"""Decimal aggregations; only the chart boundary serializes numeric strings."""

from collections import defaultdict
from datetime import timedelta
from . import ZERO, month_starts, month_label, money_it
from .ledger import period_balances
from .amounts import Cents, money, signed_cents
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from .filters import TRANSFER_IN, TRANSFER_OUT, italian_month_label

from .colors import TYPE_COLORS, vivid_category_color


def boundary_flows(transfers, account_ids):
    """Only transfer legs crossing the selected perimeter are analytical flows."""
    for t in transfers:
        source, destination = (
            t.source_id in account_ids,
            t.destination_id in account_ids,
        )
        if source != destination:
            yield t, TRANSFER_OUT if source else TRANSFER_IN


def flow_groups(filters):
    """One row per month/type/category/subcategory, aggregated by the database."""
    qs = (
        filters.transactions()
        .order_by()
        .annotate(month=TruncMonth("date"))
        .values(
            "month",
            "kind",
            "subcategory__category__name",
            "subcategory__category__color",
            "subcategory__name",
        )
        .annotate(total=Sum(Cents("amount")), count=Count("pk"))
    )
    for row in qs.iterator(chunk_size=1000):
        cat = row["subcategory__category__name"]
        yield (
            row["month"],
            money(row["total"]),
            row["kind"],
            cat,
            vivid_category_color(row["subcategory__category__color"]),
            f"{cat} · {row['subcategory__name']}",
            row["count"],
        )
    for kind, qs in boundary_queries(filters):
        for row in (
            qs.order_by()
            .annotate(month=TruncMonth("date"))
            .values("month")
            .annotate(total=Sum(Cents("amount")), count=Count("pk"))
        ):
            yield row["month"], money(row["total"]), kind, "Giroconto", TYPE_COLORS[
                kind
            ], "Giroconto", row["count"]


def boundary_queries(filters):
    for kind, own, other in (
        (TRANSFER_IN, "destination_id", "source_id"),
        (TRANSFER_OUT, "source_id", "destination_id"),
    ):
        if kind in filters.kinds:
            yield kind, filters.transfers().filter(
                **{own + "__in": filters.account_ids}
            ).exclude(**{other + "__in": filters.account_ids})


def daily_flows(filters):
    deltas = defaultdict(lambda: ZERO)
    for row in (
        filters.transactions()
        .order_by()
        .values("date")
        .annotate(total=Sum(signed_cents()))
    ):
        deltas[row["date"]] += money(row["total"])
    for kind, qs in boundary_queries(filters):
        for row in qs.order_by().values("date").annotate(total=Sum(Cents("amount"))):
            deltas[row["date"]] += money(row["total"]) * (
                1 if kind == TRANSFER_IN else -1
            )
    return deltas


def analytics(filters, *, with_balance=False, detail="categoria"):
    records = flow_groups(filters)
    transaction_count = 0
    months = month_starts(filters.start, filters.end)
    monthly = {
        m: {"month": m, "income": ZERO, "outgoing": ZERO, "net": ZERO} for m in months
    }
    breakdown = {}
    by_type, by_category, spending = [
        defaultdict(lambda: defaultdict(lambda: ZERO)) for _ in range(3)
    ]
    category_colors = {}
    income = outgoing = transfers_in = transfers_out = ZERO
    for day, amount, kind, cat, color, sub, count in records:
        transaction_count += count
        month = day.replace(day=1)
        incoming = kind in {"Entrata", TRANSFER_IN}
        side = "income" if incoming else "outgoing"
        monthly[month][side] += amount
        by_type[(side, kind)][month] += amount
        by_category[(side, cat)][month] += amount
        category_colors[cat] = color
        if incoming:
            income += amount
        else:
            outgoing += amount
            row = breakdown.setdefault(
                cat, {"name": cat, "color": color, "amount": ZERO, "count": 0}
            )
            row["amount"] += amount
            row["count"] += count
            key = sub if detail == "sottocategoria" else cat
            spending[key][month] += amount
            category_colors[key] = color
        if kind == TRANSFER_IN:
            transfers_in += amount
        elif kind == TRANSFER_OUT:
            transfers_out += amount
    for row in monthly.values():
        row["net"] = row["income"] - row["outgoing"]
    rows = sorted(breakdown.values(), key=lambda r: (-r["amount"], r["name"]))
    for row in rows:
        row["percent"] = row["amount"] / outgoing * 100 if outgoing else ZERO
        row["percent_display"] = f"{row['percent']:.1f}%".replace(".", ",")
        row["amount_display"] = money_it(row["amount"])
        row["average"] = row["amount"] / len(months)
    labels = [month_label(m) for m in months]

    def trace(name, amounts, color, **kw):
        return dict(
            type="bar",
            name=name,
            x=labels,
            y=[str(v) for v in amounts],
            marker={"color": color},
            customdata=[money_it(v) for v in amounts],
            hoverinfo="none",
            **kw,
        )

    charts = {
        "flows": {
            "totale": [
                trace(
                    "Entrate",
                    [monthly[m]["income"] for m in months],
                    TYPE_COLORS["Entrata"],
                    offsetgroup="income",
                ),
                trace(
                    "Uscite",
                    [monthly[m]["outgoing"] for m in months],
                    TYPE_COLORS["Uscita necessaria"],
                    offsetgroup="outgoing",
                ),
            ],
            "tipo": [
                trace(
                    kind, [sums[m] for m in months], TYPE_COLORS[kind], offsetgroup=side
                )
                for (side, kind), sums in sorted(by_type.items())
            ],
            "categoria": [
                trace(
                    cat,
                    [sums[m] for m in months],
                    category_colors[cat],
                    offsetgroup=side,
                )
                for (side, cat), sums in sorted(by_category.items())
            ],
        },
        "net": [
            trace(
                "Differenza netta",
                [monthly[m]["net"] for m in months],
                [
                    (
                        TYPE_COLORS["Entrata"]
                        if monthly[m]["net"] >= 0
                        else TYPE_COLORS["Uscita necessaria"]
                    )
                    for m in months
                ],
            )
        ],
        "spending": [
            trace(key, [sums[m] for m in months], category_colors[key])
            for key, sums in sorted(spending.items())
        ],
        "donut": [
            {
                "type": "pie",
                "labels": [r["name"] for r in rows],
                "values": [str(r["amount"]) for r in rows],
                "hole": 0.76,
                "sort": False,
                "textinfo": "none",
                "marker": {"colors": [r["color"] for r in rows]},
                "customdata": [
                    [r["amount_display"], r["percent_display"], r["count"]]
                    for r in rows
                ],
                "hoverinfo": "none",
            }
        ],
    }
    context = dict(
        income=income,
        outgoing=outgoing,
        net=income - outgoing,
        transfers_in=transfers_in,
        transfers_out=transfers_out,
        transfers_net=transfers_in - transfers_out,
        transaction_count=transaction_count,
        monthly_flow_data=list(monthly.values()),
        month_count=len(months),
        donut_rows=rows,
        donut_total=outgoing,
        monthly_table=(
            [
                dict(
                    name=name,
                    color=category_colors[name],
                    amount=sum(values.values(), ZERO),
                    average=sum(values.values(), ZERO) / len(months),
                )
                for name, values in spending.items()
            ]
            if detail == "sottocategoria"
            else rows
        ),
        charts=charts,
        detail=detail,
        month_choices=[
            {"value": m.strftime("%Y-%m"), "label": italian_month_label(m)}
            for m in reversed(month_starts(filters.earliest, filters.today))
        ],
    )
    if with_balance:
        ledger = period_balances(
            filters.account_ids,
            start=filters.start,
            end=filters.end,
            as_of=filters.today,
        )
        running, day, days, amounts = ledger.opening, filters.start, [], []
        deltas = daily_flows(filters)
        while day <= filters.end:
            running += deltas[day]
            days.append(day.isoformat())
            amounts.append(running)
            day += timedelta(days=1)
        charts["daily"] = [
            {
                "type": "scatter",
                "mode": "lines",
                "name": "Saldo",
                "x": days,
                "y": [str(v) for v in amounts],
                "customdata": [money_it(v) for v in amounts],
                "line": {
                    "color": "#1748b5",
                    "width": 3,
                    "shape": "spline",
                    "smoothing": 0.35,
                },
                "fill": "tozeroy",
                "fillcolor": "rgba(30,83,186,0.08)",
                "hoverinfo": "none",
            }
        ]
        context.update(
            current=ledger.current,
            opening=ledger.opening,
            closing=ledger.closing,
            today_label=filters.today.strftime("%d/%m/%Y"),
        )
    return context
