import heapq
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, time as time_type
from decimal import Decimal
from django.db.models import Q, Value
from django.db.models.functions import Coalesce
from ..models import Account, Transaction, Transfer

ZERO = Decimal("0.00")


def _ledger_sort_key(event):
    day, operation_time, order_index, priority, tie = event[:5]
    return day, operation_time or time_type.min, order_index, priority, tie


def ledger_events(start=None, end=None, account_ids=None):
    """Yield ledger deltas in chronological order without buffering the ledger."""
    txs = Transaction.objects.order_by(
        "date",
        Coalesce("operation_time", Value(time_type.min)),
        "order_index",
        "id",
    )
    transfers = Transfer.objects.order_by(
        "date",
        Coalesce("operation_time", Value(time_type.min)),
        "order_index",
        "id",
    )
    if start:
        txs = txs.filter(date__gte=start)
        transfers = transfers.filter(date__gte=start)
    if end:
        txs = txs.filter(date__lte=end)
        transfers = transfers.filter(date__lte=end)
    if account_ids is not None:
        account_ids = set(account_ids)
        txs = txs.filter(account_id__in=account_ids)
        transfers = transfers.filter(
            Q(source_id__in=account_ids) | Q(destination_id__in=account_ids)
        )

    def transaction_events():
        for transaction in txs.iterator(chunk_size=2000):
            delta = (
                transaction.amount
                if transaction.kind == "Entrata"
                else -transaction.amount
            )
            yield (
                transaction.date,
                transaction.operation_time,
                transaction.order_index,
                1,
                transaction.id,
                transaction.account_id,
                delta,
                ("transaction", transaction.id),
            )

    def transfer_events():
        for transfer in transfers.iterator(chunk_size=2000):
            if account_ids is None or transfer.source_id in account_ids:
                yield (
                    transfer.date,
                    transfer.operation_time,
                    transfer.order_index,
                    0,
                    transfer.id * 2,
                    transfer.source_id,
                    -transfer.amount,
                    ("transfer_out", transfer.id),
                )
            if account_ids is None or transfer.destination_id in account_ids:
                yield (
                    transfer.date,
                    transfer.operation_time,
                    transfer.order_index,
                    0,
                    transfer.id * 2 + 1,
                    transfer.destination_id,
                    transfer.amount,
                    ("transfer_in", transfer.id),
                )

    merged = heapq.merge(transaction_events(), transfer_events(), key=_ledger_sort_key)
    for (
        day,
        _operation_time,
        order,
        _priority,
        tie,
        account_id,
        delta,
        event_ref,
    ) in merged:
        yield day, order, event_ref[0], tie, account_id, delta, event_ref


@dataclass(slots=True)
class LedgerSnapshot:
    """Balances and event-side balances calculated in one ledger traversal."""

    opening: Decimal
    closing: Decimal
    current: Decimal
    chart_opening: Decimal
    transaction_balances: dict = field(default_factory=dict)
    transfer_balances: dict = field(default_factory=dict)
    daily_deltas: dict = field(default_factory=lambda: defaultdict(lambda: ZERO))


def ledger_snapshot(account_ids=None, *, start, end, as_of, chart_start=None):
    """Calculate period totals, current balance, chart deltas and row balances once."""
    selected_ids = set(account_ids) if account_ids is not None else None
    accounts = (
        Account.objects.all()
        if selected_ids is None
        else Account.objects.filter(id__in=selected_ids)
    )
    current_by_account = {account.id: account.initial_balance for account in accounts}
    initial_total = sum(current_by_account.values(), ZERO)
    running_total = initial_total

    opening = closing = current = chart_opening = initial_total
    chart_start = chart_start or start
    transaction_balances = {}
    transfer_balances = {}
    daily_deltas = defaultdict(lambda: ZERO)

    for day, _order, kind, _tie, account_id, delta, event_ref in ledger_events(
        account_ids=selected_ids
    ):
        current_by_account[account_id] = (
            current_by_account.get(account_id, ZERO) + delta
        )
        running_total += delta
        if kind == "transaction":
            transaction_balances[event_ref[1]] = (
                current_by_account[account_id],
                running_total,
            )
        elif kind in {"transfer_out", "transfer_in"}:
            transfer_balances[(event_ref[1], kind)] = current_by_account[account_id]

        if day < start:
            opening += delta
        if day <= end:
            closing += delta
        if day <= as_of:
            current += delta
        if day < chart_start:
            chart_opening += delta
        if chart_start <= day <= as_of:
            daily_deltas[day] += delta

    return LedgerSnapshot(
        opening=opening,
        closing=closing,
        current=current,
        chart_opening=chart_opening,
        transaction_balances=transaction_balances,
        transfer_balances=transfer_balances,
        daily_deltas=daily_deltas,
    )


def initial_balance(account_ids=None):
    qs = Account.objects.all()
    if account_ids is not None:
        qs = qs.filter(id__in=account_ids)
    return sum((x.initial_balance for x in qs), ZERO)


def balance_before(day, account_ids=None):
    return period_balances(account_ids, start=day, end=day, as_of=day).opening


def balance_at(day, account_ids=None):
    return period_balances(account_ids, start=day, end=day, as_of=day).closing


def period_balances(account_ids, *, start, end, as_of):
    """Three SQL aggregates; no transaction instances or per-row balance maps."""
    from django.db.models import Sum
    from .amounts import Cents, money, signed_cents

    ids = (
        set(account_ids)
        if account_ids is not None
        else set(Account.objects.values_list("id", flat=True))
    )
    opening = initial_balance(ids)
    result = {key: opening for key in ("opening", "closing", "current")}
    bounds = {
        "opening": Q(date__lt=start),
        "closing": Q(date__lte=end),
        "current": Q(date__lte=as_of),
    }
    queries = [
        (Transaction.objects.filter(account_id__in=ids), signed_cents(), 1),
        (
            Transfer.objects.filter(destination_id__in=ids).exclude(source_id__in=ids),
            Cents("amount"),
            1,
        ),
        (
            Transfer.objects.filter(source_id__in=ids).exclude(destination_id__in=ids),
            Cents("amount"),
            -1,
        ),
    ]
    for qs, expr, sign in queries:
        sums = qs.filter(date__lte=max(start, end, as_of)).aggregate(
            **{key: Sum(expr, filter=condition) for key, condition in bounds.items()}
        )
        for key in result:
            result[key] += sign * money(sums[key])
    return LedgerSnapshot(**result, chart_opening=result["opening"])


def balances_after_transactions(account_id=None, account_ids=None):
    """Balance following each movement, including transfer events before it."""
    ids = {account_id} if account_id is not None else account_ids
    snapshot = ledger_snapshot(
        ids,
        start=date.max,
        end=date.max,
        as_of=date.max,
    )
    balance_index = 0 if account_id is not None else 1
    return {
        transaction_id: balances[balance_index]
        for transaction_id, balances in snapshot.transaction_balances.items()
    }


def balances_after_transfer_legs(account_id=None):
    """Return each transfer leg's balance for the account shown on that row."""
    ids = {account_id} if account_id is not None else None
    return ledger_snapshot(
        ids, start=date.max, end=date.max, as_of=date.max
    ).transfer_balances


def next_order_index():
    t = (
        Transaction.objects.order_by("-order_index")
        .values_list("order_index", flat=True)
        .first()
        or 0
    )
    r = (
        Transfer.objects.order_by("-order_index")
        .values_list("order_index", flat=True)
        .first()
        or 0
    )
    return max(t, r) + 1
