"""SQL union of transactions and transfer legs with per-account running balances.

All predicates from user input are compiled by the ORM; sort identifiers come
from a fixed allowlist. Window sums run before visibility filters, so searching
or hiding a category cannot change the balance displayed on a visible row.
"""

from functools import cached_property
from datetime import date
from django.core.exceptions import EmptyResultSet
from django.db import connection
from .amounts import money
from .filters import TRANSFER_IN, TRANSFER_OUT


class MovementQuery:
    ordered = True

    def __init__(self, filters, sort, hydrate):
        self.filters, self.sort, self.hydrate = filters, sort, hydrate
        ids = sorted(filters.account_ids)
        slots = ",".join(["%s"] * len(ids)) or "NULL"
        # Table names are model constants, not user-provided identifiers.
        self.events = f"""WITH events AS (
            SELECT id AS event_id, 0 AS leg, account_id, date AS day,
                operation_time AS clock, order_index AS ordinal, 1 AS priority, id AS tie,
                CASE WHEN kind = 'Entrata' THEN 1 ELSE -1 END * CAST(ROUND(amount * 100) AS BIGINT) AS delta
            FROM wallet_transaction WHERE account_id IN ({slots}) AND date <= %s
            UNION ALL
            SELECT id, 1, source_id, date, operation_time, order_index, 0, id * 2,
                -CAST(ROUND(amount * 100) AS BIGINT)
            FROM wallet_transfer WHERE source_id IN ({slots}) AND date <= %s
            UNION ALL
            SELECT id, 2, destination_id, date, operation_time, order_index, 0, id * 2 + 1,
                CAST(ROUND(amount * 100) AS BIGINT)
            FROM wallet_transfer WHERE destination_id IN ({slots}) AND date <= %s
        )"""
        self.base_params = (ids + [filters.end]) * 3

        def compiled(qs):
            try:
                return qs.order_by().values("pk").query.sql_with_params()
            except EmptyResultSet:
                return "SELECT NULL WHERE 1 = 0", ()

        tx_sql, tx_params = compiled(filters.transactions())
        tr_sql, tr_params = compiled(filters.transfers())
        transfer_legs = []
        if TRANSFER_OUT in filters.kinds:
            transfer_legs.append(1)
        if TRANSFER_IN in filters.kinds:
            transfer_legs.append(2)
        leg_sql = ",".join(map(str, transfer_legs)) or "NULL"
        self.visible = f"((e.leg = 0 AND e.event_id IN ({tx_sql})) OR (e.leg IN ({leg_sql}) AND e.event_id IN ({tr_sql})))"
        self.params = self.base_params + list(tx_params) + list(tr_params)

    @cached_property
    def total_count(self):
        with connection.cursor() as cursor:
            cursor.execute(
                self.events + " SELECT COUNT(*) FROM events e WHERE " + self.visible,
                self.params,
            )
            return cursor.fetchone()[0]

    def count(self):
        return self.total_count

    def __len__(self):
        return self.total_count

    def __getitem__(self, item):
        if not isinstance(item, slice) or item.step not in (None, 1):
            raise TypeError("MovementQuery supports contiguous page slices only")
        start = item.start or 0
        if start < 0 or item.stop is None or item.stop < start:
            raise ValueError("Invalid page interval")
        return list(self.fetch(limit=item.stop - start, offset=start))

    def __iter__(self):
        return self.fetch()

    def fetch(self, limit=None, offset=0):
        sorts = {
            "date": "e.day",
            "description": "LOWER(COALESCE(t.description, g.description))",
            "amount": "e.delta",
            "kind": "CASE WHEN e.leg = 0 THEN t.kind WHEN e.leg = 1 THEN 'Trasferimento in uscita' ELSE 'Trasferimento in entrata' END",
            "account": "a.name",
            "category": "COALESCE(c.name, 'Giroconto')",
            "subcategory": "COALESCE(s.name, '—')",
            "balance": "balance_cents",
        }
        direction = "DESC" if self.sort.startswith("-") else "ASC"
        ordering = ", ".join(
            f"{field} {direction}"
            for field in [
                sorts[self.sort.lstrip("-")],
                "e.day",
                "COALESCE(e.clock, '00:00:00')",
                "e.ordinal",
                "e.priority",
                "e.tie",
            ]
        )
        sql = self.events + f""", ranked AS (
            SELECT events.*, SUM(delta) OVER (
                PARTITION BY account_id ORDER BY day, COALESCE(clock, '00:00:00'), ordinal, priority, tie
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running
            FROM events
        )
        SELECT e.event_id, e.leg, e.running + CAST(ROUND(a.initial_balance * 100) AS BIGINT) AS balance_cents
        FROM ranked e JOIN wallet_account a ON a.id = e.account_id
        LEFT JOIN wallet_transaction t ON e.leg = 0 AND t.id = e.event_id
        LEFT JOIN wallet_transfer g ON e.leg <> 0 AND g.id = e.event_id
        LEFT JOIN wallet_subcategory s ON s.id = t.subcategory_id
        LEFT JOIN wallet_category c ON c.id = s.category_id
        WHERE {self.visible} ORDER BY {ordering}"""
        params = list(self.params)
        if limit is not None:
            sql += " LIMIT %s OFFSET %s"
            params += [limit, offset]
        # Django's regular PostgreSQL cursor buffers results; paged requests use
        # LIMIT, while explicit "all" / CSV exports necessarily scale with output.
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            while batch := cursor.fetchmany(400):
                yield from self.hydrate(batch)

    def daily_totals(self):
        sql = self.events + f""" SELECT e.day,
            SUM(CASE WHEN delta > 0 THEN delta ELSE 0 END),
            SUM(CASE WHEN delta < 0 THEN -delta ELSE 0 END)
            FROM events e WHERE {self.visible} GROUP BY e.day"""
        with connection.cursor() as cursor:
            cursor.execute(sql, self.params)
            return [
                (
                    day if isinstance(day, date) else date.fromisoformat(day),
                    money(income),
                    money(outgoing),
                )
                for day, income, outgoing in cursor.fetchall()
            ]
