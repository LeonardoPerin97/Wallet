"""Unified register with both transfer legs and chronological balances."""

from collections import defaultdict
from datetime import time
from types import SimpleNamespace
from ..icon_config import icon_for_subcategory, glyph_for_icon
from . import ZERO
from .filters import TRANSFER_IN, TRANSFER_OUT, italian_month_label
from .colors import TYPE_COLORS, vivid_category_color


def movement_rows(filters, sort="-date"):
    from .movement_query import MovementQuery

    if sort.lstrip("-") not in {
        "date",
        "description",
        "amount",
        "kind",
        "account",
        "category",
        "subcategory",
        "balance",
    }:
        sort = "-date"
    return MovementQuery(filters, sort, _hydrate), sort


def _hydrate(batch):
    from ..models import Transaction, Transfer
    from .amounts import money

    txs = {
        t.pk: t
        for t in Transaction.objects.filter(
            pk__in=[pk for pk, leg, _ in batch if leg == 0]
        ).select_related("account", "subcategory__category")
    }
    transfers = {
        t.pk: t
        for t in Transfer.objects.filter(
            pk__in=[pk for pk, leg, _ in batch if leg]
        ).select_related("source", "destination")
    }
    for pk, leg, balance in batch:
        if not leg:
            t = txs[pk]
            t.is_transfer = False
            t.is_positive = t.kind == "Entrata"
            t.display_type, t.display_category, t.display_subcategory = (
                t.kind,
                t.category.name,
                t.subcategory.name,
            )
            t.category_color = vivid_category_color(t.category.color)
            t.icon_glyph = glyph_for_icon(
                icon_for_subcategory(t.subcategory.name, t.subcategory.icon)
            )
            t.counterparty = None
            t.balance_after = money(balance)
            t.event_priority, t.event_tie = 1, t.id
            yield t
        else:
            t = transfers[pk]
            positive = leg == 2
            account, other = (
                (t.destination, t.source) if positive else (t.source, t.destination)
            )
            kind = TRANSFER_IN if positive else TRANSFER_OUT
            label = "transfer_in" if positive else "transfer_out"
            yield SimpleNamespace(
                id=f"{pk}-{label}",
                uid=t.uid,
                is_transfer=True,
                date=t.date,
                operation_time=t.operation_time,
                order_index=t.order_index,
                description=t.description,
                amount=t.amount,
                signed_amount=t.amount if positive else -t.amount,
                kind=kind,
                direction="Entrata" if positive else "Uscita",
                display_type=kind,
                display_category="Giroconto",
                display_subcategory="—",
                account=account,
                counterparty=other,
                is_positive=positive,
                balance_after=money(balance),
                category_color=TYPE_COLORS[kind],
                icon_glyph="↔",
                notes="",
                external_id=f"giroconto:{t.uid}",
                event_priority=0,
                event_tie=pk * 2 + int(positive),
            )


def list_groups(all_items, visible_items):
    days = defaultdict(lambda: ZERO)
    months = defaultdict(lambda: {"income": ZERO, "outgoing": ZERO, "net": ZERO})
    for day, income, outgoing in all_items.daily_totals():
        days[day] = income - outgoing
        m = months[day.replace(day=1)]
        m["income"] += income
        m["outgoing"] += outgoing
        m["net"] += income - outgoing
    groups = []
    for t in sorted(
        visible_items,
        key=lambda t: (
            t.date,
            t.operation_time or time.min,
            t.order_index,
            t.event_priority,
            t.event_tie,
        ),
        reverse=True,
    ):
        month = t.date.replace(day=1)
        if not groups or groups[-1]["month"] != month:
            groups.append(
                dict(
                    month=month,
                    label=italian_month_label(month),
                    days=[],
                    **months[month],
                )
            )
        day_groups = groups[-1]["days"]
        if not day_groups or day_groups[-1]["date"] != t.date:
            day_groups.append({"date": t.date, "net": days[t.date], "rows": []})
        day_groups[-1]["rows"].append(t)
    return groups
