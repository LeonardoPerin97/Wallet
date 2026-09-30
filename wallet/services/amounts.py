"""Sum integer cents in SQL, returning Decimal only at the service boundary.

Rounding each stored two-decimal amount before SUM avoids SQLite's floating
point SUM artifacts. PostgreSQL also uses this expression, with numeric input.
"""

from decimal import Decimal
from django.db.models import BigIntegerField, Case, F, Func, Sum, When


class Cents(Func):
    template = "CAST(ROUND(%(expressions)s * 100) AS BIGINT)"
    output_field = BigIntegerField()


def signed_cents():
    return Case(
        When(kind="Entrata", then=Cents("amount")),
        default=-Cents("amount"),
        output_field=BigIntegerField(),
    )


def money(cents):
    return (Decimal(cents or 0) / 100).quantize(Decimal("0.01"))


def sum_money(queryset, field="amount"):
    return money(queryset.aggregate(total=Sum(Cents(F(field))))["total"])
