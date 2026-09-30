"""Look up only identities/signatures occurring in the current import batch."""

from django.db.models import Q
from ..models import Transaction


def signature(account, day, description, amount):
    return account, day, description.casefold(), amount


def duplicate_index(specs):
    """specs: (account PK, date, description, Decimal amount, external ID)."""
    identities, signatures = set(), set()
    specs = list(dict.fromkeys(row for row in specs if row[0] is not None))
    for offset in range(0, len(specs), 80):
        condition = Q(pk__in=[])
        for account, day, desc, amount, external in specs[offset : offset + 80]:
            match = Q(date=day, description__iexact=desc, amount=amount)
            if external:
                match |= Q(external_id=external)
            condition |= Q(account_id=account) & match
        for account, day, desc, amount, external in (
            Transaction.objects.filter(condition)
            .order_by()
            .values_list("account_id", "date", "description", "amount", "external_id")
        ):
            signatures.add(signature(account, day, desc, amount))
            if external:
                identities.add((account, external))
    return identities, signatures
