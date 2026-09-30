"""Access policy for this single-owner Wallet installation."""

from django.conf import settings


def is_wallet_owner(user):
    """Only an active Django superuser can administer the personal wallet."""
    if not user.is_authenticated or not user.is_active or not user.is_superuser:
        return False

    configured_username = getattr(settings, "WALLET_OWNER_USERNAME", "")
    return not configured_username or user.get_username() == configured_username
