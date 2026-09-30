from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from ..forms import TransactionForm, TransferForm
from ..models import Account, Subcategory, Transaction, Transfer
from ..services.filters import Filters
from ..services.colors import vivid_category_color
from ..services.movements import movement_rows, list_groups


def _movement_rows(request, sort_override=None, filter_state=None):
    filters = Filters.parse(request.GET)
    rows, sort = movement_rows(
        filters, sort_override or request.GET.get("sort", "-date")
    )
    return (
        rows,
        sort,
        next(iter(filters.account_ids)) if len(filters.account_ids) == 1 else None,
    )


@login_required
def transactions(request):
    filters = Filters.parse(request.GET)
    mode = request.GET.get("vista", "tabella")
    items, sort = movement_rows(
        filters, "-date" if mode == "lista" else request.GET.get("sort", "-date")
    )
    per_page = request.GET.get("per_pagina", "25")
    if per_page not in {"25", "50", "100", "tutti"}:
        per_page = "25"
    page = Paginator(
        items, max(1, len(items)) if per_page == "tutti" else int(per_page)
    ).get_page(request.GET.get("pagina"))
    context = filters.context()
    context.update(
        page=page,
        sort=sort,
        per_page=per_page,
        mode=mode,
        analysis_filters=True,
        movement_filters=True,
        grouped_months=list_groups(items, page.object_list),
        query=request.GET,
        page_sizes=["25", "50", "100", "tutti"],
    )
    return render(request, "wallet/transactions.html", context)


@login_required
def transaction_form(request, uid=None):
    obj = get_object_or_404(Transaction, uid=uid) if uid else None
    initial = None
    if not request.POST and not obj:
        initial = {"date": timezone.localdate()}
        account_id = request.GET.get("conto", "")
        if (
            account_id.isdigit()
            and Account.objects.filter(pk=account_id, active=True).exists()
        ):
            initial["account"] = account_id
    flow = request.POST.get("flusso", request.GET.get("flusso", ""))
    form = TransactionForm(
        request.POST or None, instance=obj, initial=initial, flow=flow
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request, "Movimento aggiornato." if obj else "Movimento aggiunto."
        )
        return redirect("transactions")
    subs_qs = Subcategory.objects.filter(active=True, category__active=True)
    if not obj and flow in {"entrata", "uscita"}:
        subs_qs = (
            subs_qs.filter(kind="Entrata")
            if flow == "entrata"
            else subs_qs.exclude(kind="Entrata")
        )
    if obj:
        subs_qs = subs_qs | Subcategory.objects.filter(pk=obj.subcategory_id)
    subcategories = list(
        subs_qs.values("id", "name", "category_id", "kind", color=F("category__color"))
    )
    categories = form.fields["category"].queryset
    for sub in subcategories:
        sub["color"] = vivid_category_color(sub["color"])
    categories_data = [
        dict(id=c.pk, name=c.name, color=vivid_category_color(c.color))
        for c in categories
    ]
    return render(
        request,
        "wallet/transaction_form.html",
        {
            "form": form,
            "obj": obj,
            "categories": categories,
            "subcategories_data": subcategories,
            "categories_data": categories_data,
            "flow": flow,
        },
    )


@require_POST
@login_required
def transaction_delete(request, uid):
    obj = get_object_or_404(Transaction, uid=uid)
    obj.delete()
    messages.success(request, "Il movimento è stato eliminato.")
    return redirect("transactions")


@login_required
def transfers(request):
    form = TransferForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request, "Giroconto registrato. Non modifica i totali consolidati."
        )
        return redirect("transactions")
    if not request.POST:
        form.initial.update({"date": timezone.localdate(), "description": "Giroconto"})
    return render(request, "wallet/transfer_form.html", {"form": form})


@login_required
def transfer_edit(request, uid):
    obj = get_object_or_404(Transfer, uid=uid)
    form = TransferForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request,
            "Giroconto aggiornato. I saldi dei due conti sono stati ricalcolati.",
        )
        return redirect("transactions")
    return render(request, "wallet/transfer_form.html", {"form": form, "obj": obj})


@require_POST
@login_required
def transfer_delete(request, uid):
    obj = get_object_or_404(Transfer, uid=uid)
    obj.delete()
    messages.success(
        request, "Giroconto eliminato. I saldi dei due conti sono stati ricalcolati."
    )
    return redirect("transactions")
