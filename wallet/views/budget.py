from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from ..services.budget import budget_context


@login_required
def budget(request):
    result = budget_context(request)
    return (
        render(request, "wallet/budget.html", result)
        if isinstance(result, dict)
        else result
    )
