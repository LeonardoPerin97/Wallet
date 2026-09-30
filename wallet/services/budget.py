"""Monthly limits, optional subcategory allocation and consolidated spending."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
import re

from django.contrib import messages
from django.db import transaction as db_transaction
from django.db.models import Prefetch, Q, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from ..models import (
    Category,
    CategoryBudget,
    Subcategory,
    SubcategoryBudget,
    OUTGOING,
    Transaction,
)
from . import ZERO, parse_money, month_starts
from .colors import TYPE_COLORS
from .amounts import Cents, money
from .filters import italian_month_label


def _month_from_request(value):
    try:
        year, month = (int(part) for part in value.split("-", 1))
        return date(year, month, 1)
    except (AttributeError, TypeError, ValueError):
        today = timezone.localdate()
        return date(today.year, today.month, 1)


def _metrics(spent, limit, has_budget):
    ratio = spent / limit * Decimal("100") if limit else ZERO
    return {
        "spent": spent,
        "limit": limit,
        "ratio": ratio,
        "has_budget": has_budget,
        "ratio_label": f"{ratio:.0f}%".replace(".", ",") if limit else "Limite zero",
        "remaining": limit - spent,
        "remaining_label": "Sforamento" if spent > limit else "Residuo",
        "remaining_display": abs(limit - spent),
        "progress": (
            str(min(100, max(0, ratio)))
            if limit
            else "100" if spent and has_budget else "0"
        ),
        "state": (
            "over"
            if has_budget and spent > limit
            else "near" if limit and ratio >= 85 else "steady"
        ),
    }


def _parse_limit(raw):
    # Match the live preview: Italian grouping or a plain decimal point.
    # A mistyped decimal such as 1,2345 must not become a 12,345-euro limit.
    normalized = re.sub(r"EUR|[€\s]", "", raw, flags=re.IGNORECASE)
    if not re.fullmatch(
        r"\+?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?|\+?\d+(?:\.\d{1,2})?",
        normalized,
    ):
        raise ValueError("Importo non valido")
    return parse_money(normalized)


def _save_budgets(request, month, categories, modes):
    """Validate the whole form before replacing either kind of limit atomically."""
    parsed, errors = [], defaultdict(list)
    for category in categories:
        subs = list(category.subcategories.all())
        fields = [f"budget_{category.id}", f"budget_mode_{category.id}"] + [
            f"subbudget_{s.id}" for s in subs
        ]
        if not any(field in request.POST for field in fields):
            continue  # An omitted category is not a request to erase its budget.
        mode = modes[category.id]
        if mode not in {"categoria", "sottocategorie"}:
            errors[category.id].append(
                "Scegli un limite unico o la suddivisione per sottocategorie."
            )
            continue
        targets = (
            [(category, f"budget_{category.id}")]
            if mode == "categoria"
            else [(s, f"subbudget_{s.id}") for s in subs]
        )
        amounts = []
        for obj, field in targets:
            raw = request.POST.get(field, "").strip()
            try:
                amount = _parse_limit(raw) if raw else None
                if amount is not None and amount < ZERO:
                    raise ValueError("importo negativo")
                amounts.append((obj, amount))
            except ValueError:
                errors[category.id].append(
                    f"{obj.name}: inserisci un importo pari o superiore a zero, con al massimo due decimali."
                )
        parsed.append((category, mode, amounts))
    if errors:
        messages.error(
            request, "Controlla gli importi: nessun budget è stato modificato."
        )
        return errors
    with db_transaction.atomic():
        # Serialize concurrent edits of the same categories on PostgreSQL.
        list(
            Category.objects.select_for_update()
            .filter(pk__in=[category.pk for category, _, _ in parsed])
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        for category, mode, amounts in parsed:
            # A category/month has one source of truth: a single limit OR its lines.
            CategoryBudget.objects.filter(month=month, category=category).delete()
            SubcategoryBudget.objects.filter(
                month=month, subcategory__category=category
            ).delete()
            for obj, amount in amounts:
                if amount is None:
                    continue
                if mode == "categoria":
                    CategoryBudget.objects.create(
                        month=month, category=obj, amount=amount
                    )
                else:
                    SubcategoryBudget.objects.create(
                        month=month, subcategory=obj, amount=amount
                    )
    messages.success(request, "Budget mensili aggiornati.")
    return redirect(f"{reverse('budget')}?mese={month:%Y-%m}")


def budget_context(request):
    today = timezone.localdate()
    selected_month = _month_from_request(
        request.POST.get("mese")
        if request.method == "POST"
        else request.GET.get("mese")
    )
    categories = list(
        Category.objects.filter(
            Q(subcategories__kind__in=OUTGOING)
            | Q(monthly_budgets__month=selected_month)
            | Q(subcategories__monthly_budgets__month=selected_month)
        )
        .distinct()
        .order_by("name")
        .prefetch_related(
            Prefetch(
                "subcategories",
                queryset=Subcategory.objects.filter(kind__in=OUTGOING).order_by("name"),
            )
        )
    )
    manual_limits = {
        b.category_id: b.amount
        for b in CategoryBudget.objects.filter(month=selected_month)
    }
    sub_limits, allocated_limits = {}, defaultdict(lambda: ZERO)
    for budget in SubcategoryBudget.objects.filter(month=selected_month).select_related(
        "subcategory"
    ):
        sub_limits[budget.subcategory_id] = budget.amount
        allocated_limits[budget.subcategory.category_id] += budget.amount
    budget_map = {**manual_limits, **allocated_limits}
    modes = {
        c.id: request.POST.get(
            f"budget_mode_{c.id}",
            "sottocategorie" if c.id in allocated_limits else "categoria",
        )
        for c in categories
    }
    errors = {}
    if request.method == "POST" and request.POST.get("azione") == "salva_budget":
        result = _save_budgets(request, selected_month, categories, modes)
        if not isinstance(result, dict):
            return result
        errors = result

    def input_value(name, value):
        if errors and name in request.POST:
            return request.POST[name]
        return f"{value:.2f}".replace(".", ",") if value is not None else ""

    next_month = date(
        selected_month.year + (selected_month.month == 12),
        1 if selected_month.month == 12 else selected_month.month + 1,
        1,
    )
    period_end = max(selected_month, min(today, next_month - timedelta(days=1)))
    previous_month = date(
        selected_month.year - (selected_month.month == 1),
        12 if selected_month.month == 1 else selected_month.month - 1,
        1,
    )
    previous_end = selected_month - timedelta(days=1)
    if selected_month == date(today.year, today.month, 1):
        previous_end = previous_month + timedelta(
            days=min(today.day, previous_end.day) - 1
        )

    actuals, sub_actuals = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    txs = Transaction.objects.filter(
        date__gte=selected_month, date__lte=period_end, kind__in=OUTGOING
    )
    for row in (
        txs.order_by()
        .values("subcategory_id", "subcategory__category_id")
        .annotate(total=Sum(Cents("amount")))
    ):
        amount = money(row["total"])
        sub_actuals[row["subcategory_id"]] = amount
        actuals[row["subcategory__category_id"]] += amount
    actual_total = sum(actuals.values(), ZERO)
    total_budget = sum(budget_map.values(), ZERO)
    current_types = {
        r["kind"]: money(r["total"])
        for r in Transaction.objects.filter(
            date__gte=selected_month, date__lte=period_end
        )
        .order_by()
        .values("kind")
        .annotate(total=Sum(Cents("amount")))
    }
    previous_types = {
        r["kind"]: money(r["total"])
        for r in Transaction.objects.filter(
            date__gte=previous_month, date__lte=previous_end
        )
        .order_by()
        .values("kind")
        .annotate(total=Sum(Cents("amount")))
    }
    income = current_types.get("Entrata", ZERO)
    previous_outgoing = sum((previous_types.get(k, ZERO) for k in OUTGOING), ZERO)
    budget_rows = []
    for category in categories:
        row = _metrics(
            actuals[category.id],
            budget_map.get(category.id, ZERO),
            category.id in budget_map,
        )
        row.update(
            category=category,
            mode=modes[category.id],
            errors=errors.get(category.id, []),
            input_value=input_value(
                f"budget_{category.id}", manual_limits.get(category.id)
            ),
            subcategories=[],
        )
        for sub in category.subcategories.all():
            detail = _metrics(
                sub_actuals[sub.id], sub_limits.get(sub.id, ZERO), sub.id in sub_limits
            )
            detail.update(
                subcategory=sub,
                input_value=input_value(f"subbudget_{sub.id}", sub_limits.get(sub.id)),
            )
            row["subcategories"].append(detail)
        budget_rows.append(row)

    type_rows = []
    for kind in ("Uscita necessaria", "Uscita extra", "Investimento"):
        amount, previous = current_types.get(kind, ZERO), previous_types.get(kind, ZERO)
        share = amount / actual_total * Decimal("100") if actual_total else ZERO
        income_share = amount / income * Decimal("100") if income else ZERO
        change = (
            ((amount - previous) / previous * Decimal("100"))
            if previous
            else (Decimal("100") if amount else ZERO)
        )
        type_rows.append(
            {
                "name": kind,
                "amount": amount,
                "share": share,
                "income_share": income_share,
                "previous": previous,
                "change": change,
                "color": TYPE_COLORS[kind],
                "share_display": f"{share:.1f}%".replace(".", ","),
                "income_share_display": f"{income_share:.1f}%".replace(".", ","),
                "change_display": f"{change:+.1f}%".replace(".", ","),
                "share_bar_width": f"{min(Decimal('100'), max(ZERO, share)):.1f}",
            }
        )
    net = income - actual_total
    budget_ratio = (
        actual_total / total_budget * Decimal("100") if total_budget else ZERO
    )
    history_start = date(selected_month.year - 1, selected_month.month, 1)
    historical_actuals = {
        r["month"]: money(r["spent"])
        for r in Transaction.objects.filter(
            date__gte=history_start, date__lt=selected_month, kind__in=OUTGOING
        )
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(spent=Sum(Cents("amount")))
    }
    historical_budgets = defaultdict(lambda: ZERO)
    for model in (CategoryBudget, SubcategoryBudget):
        for row in (
            model.objects.filter(month__gte=history_start, month__lt=selected_month)
            .order_by()
            .values("month")
            .annotate(limit=Sum(Cents("amount")))
        ):
            historical_budgets[row["month"]] += money(row["limit"])
    history = [
        {
            "month": m.strftime("%Y-%m"),
            "label": italian_month_label(m),
            **_metrics(historical_actuals.get(m, ZERO), historical_budgets[m], True),
        }
        for m in reversed(month_starts(history_start, previous_month))
    ]
    return {
        "history": history,
        "month": selected_month,
        "month_value": selected_month.strftime("%Y-%m"),
        "month_label": italian_month_label(selected_month),
        "month_end": period_end,
        "budget_rows": budget_rows,
        "type_rows": type_rows,
        "income": income,
        "outgoing": actual_total,
        "net": net,
        "total_budget": total_budget,
        "remaining": total_budget - actual_total,
        "remaining_label": "Sforamento" if actual_total > total_budget else "Residuo",
        "remaining_display": abs(total_budget - actual_total),
        "previous_outgoing": previous_outgoing,
        "budget_ratio": budget_ratio,
        "total_income_share_display": f"{(actual_total / income * Decimal('100') if income else ZERO):.1f}%".replace(
            ".", ","
        ),
        "income_residual_share": net / income * Decimal("100") if income else ZERO,
        "income_residual_share_display": f"{(net / income * Decimal('100') if income else ZERO):.1f}%".replace(
            ".", ","
        ),
    }
