"""Prevent authenticated non-owner accounts from sharing the wallet."""

from django.contrib.auth import logout
from django.shortcuts import redirect

from .access import is_wallet_owner


class SingleOwnerMiddleware:
    """End sessions that do not belong to the configured wallet owner."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not is_wallet_owner(request.user):
            logout(request)
            return redirect("login")
        return self.get_response(request)
