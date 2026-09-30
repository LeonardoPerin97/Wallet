from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from ..forms import AccountForm, CategoryForm, SubcategoryForm, TaxonomyImportForm
from ..models import Account, Category, Subcategory
from ..services import import_taxonomy


@login_required
def settings_page(request):
    obj = (
        get_object_or_404(Account, pk=request.GET["modifica"])
        if request.GET.get("modifica", "").isdigit()
        else None
    )
    if request.method == "POST" and request.POST.get("account_id", "").isdigit():
        obj = get_object_or_404(Account, pk=request.POST["account_id"])
    form = AccountForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Conto aggiornato." if obj else "Conto aggiunto.")
        return redirect("settings")
    today = timezone.localdate()
    accounts = list(Account.objects.all())
    # One ledger traversal for all per-account closing balances.
    from ..services.ledger import ledger_events

    balances = {a.id: a.initial_balance for a in accounts}
    for _, _, _, _, account_id, delta, _ in ledger_events(end=today):
        balances[account_id] += delta
    for a in accounts:
        a.current_balance = balances[a.id]
    return render(
        request,
        "wallet/settings.html",
        {"accounts": accounts, "form": form, "editing_account": obj},
    )


@login_required
def categories_page(request):
    edit = request.GET.get("modifica", "")
    edit_sub = request.GET.get("sottocategoria", "")
    category = get_object_or_404(Category, pk=edit) if edit.isdigit() else None
    sub = get_object_or_404(Subcategory, pk=edit_sub) if edit_sub.isdigit() else None
    action = request.POST.get("action")
    if action == "category" and request.POST.get("object_id", "").isdigit():
        category = get_object_or_404(Category, pk=request.POST["object_id"])
    if action == "subcategory" and request.POST.get("object_id", "").isdigit():
        sub = get_object_or_404(Subcategory, pk=request.POST["object_id"])
    category_form = CategoryForm(
        request.POST if action == "category" else None, instance=category
    )
    subcategory_form = SubcategoryForm(
        request.POST if action == "subcategory" else None, instance=sub
    )
    upload_form = (
        TaxonomyImportForm(request.POST, request.FILES)
        if request.method == "POST" and action not in {"category", "subcategory"}
        else TaxonomyImportForm()
    )
    if request.method == "POST":
        form = (
            category_form
            if action == "category"
            else subcategory_form if action == "subcategory" else upload_form
        )
        if form.is_valid():
            try:
                if form is upload_form:
                    count = import_taxonomy(form.cleaned_data["file"])
                    messages.success(
                        request,
                        f"Tassonomia aggiornata: importate {count} sottocategorie.",
                    )
                else:
                    form.save()
                    messages.success(
                        request,
                        (
                            "Categoria aggiornata."
                            if action == "category"
                            else "Sottocategoria aggiornata."
                        ),
                    )
                return redirect("categories")
            except ValueError as exc:
                form.add_error(None, str(exc))
    return render(
        request,
        "wallet/categories.html",
        {
            "categories": Category.objects.prefetch_related("subcategories").all(),
            "form": upload_form,
            "category_form": category_form,
            "subcategory_form": subcategory_form,
            "editing_category": category,
            "editing_subcategory": sub,
        },
    )
