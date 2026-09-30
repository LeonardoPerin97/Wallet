from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, QueryDict
from django.shortcuts import render
from ..services.filters import Filters
from ..services.analytics import analytics
from ..models import UserPreference


def _page_filters(request, *, categories):
    # Keep the existing session keys so the URL rename preserves saved filters.
    key = "wallet_dashboard_filters" if categories else "wallet_home_filters"
    params = QueryDict(request.session.get(key, ""), mutable=True)
    if not params and not categories:
        previous = UserPreference.objects.filter(pk=1).first()
        if previous:
            params["periodo"] = previous.period
            if previous.start_date:
                params["inizio"] = previous.start_date.isoformat()
            if previous.end_date:
                params["fine"] = previous.end_date.isoformat()
            saved = list(previous.accounts.values_list("id", flat=True))
            if previous.no_accounts_selected:
                params["conto"] = ""
            elif saved:
                params.setlist("conto", [str(i) for i in saved])
            elif previous.account_id:
                params["conto"] = str(previous.account_id)
    if request.GET:
        if "periodo" in request.GET and "conto" in request.GET:
            params = request.GET.copy()
        else:
            for k in request.GET:
                params.setlist(k, request.GET.getlist(k))
        if "periodo" not in request.GET and (
            "inizio" in request.GET or "fine" in request.GET
        ):
            params["periodo"] = "custom"
        request.session[key] = params.urlencode()
    request.wallet_params = params
    filters = Filters.parse(params, categories=categories)
    if request.GET and not categories:
        previous, _ = UserPreference.objects.get_or_create(pk=1)
        previous.period = filters.period
        previous.start_date, previous.end_date = filters.start, filters.end
        previous.account_id = (
            next(iter(filters.account_ids)) if len(filters.account_ids) == 1 else None
        )
        previous.no_accounts_selected = not filters.account_ids
        previous.save()
        previous.accounts.set(
            filters.account_ids
            if filters.account_ids != {a.id for a in filters.accounts}
            else []
        )
    return filters


@login_required
def dashboard(request):
    filters = _page_filters(request, categories=False)
    context = filters.context()
    context.update(analytics(filters, with_balance=True))
    return render(request, "wallet/home.html", context)


@login_required
def overview(request):
    filters = _page_filters(request, categories=True)
    detail = request.GET.get("dettaglio", "categoria")
    if detail not in {"categoria", "sottocategoria"}:
        detail = "categoria"
    context = filters.context()
    context.update(analytics(filters, detail=detail))
    sort = request.GET.get("ordine", "-amount")
    key = sort.lstrip("-")
    if key not in {"name", "amount", "average"}:
        key, sort = "amount", "-amount"
    context["monthly_table"] = sorted(
        context["monthly_table"], key=lambda r: r[key], reverse=sort.startswith("-")
    )
    context.update(analysis_filters=True, sort=sort)
    return render(request, "wallet/dashboard.html", context)


@login_required
def overview_expense_data(request):
    params = request.GET.copy()
    if params.get("spese_inizio") or params.get("spese_fine"):
        params["periodo"] = "custom"
        params["inizio"], params["fine"] = params.get("spese_inizio", ""), params.get(
            "spese_fine", ""
        )
    filters = Filters.parse(params)
    if filters.error:
        return JsonResponse({"error": filters.error}, status=400)
    result = analytics(filters)
    return JsonResponse(
        {
            "rows": result["donut_rows"],
            "total": result["outgoing"],
            "range": f"{filters.start:%d/%m/%Y} – {filters.end:%d/%m/%Y}",
        }
    )
