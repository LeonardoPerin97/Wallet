"""Populate only an explicitly selected, empty demonstration database."""

import calendar
from datetime import date
from decimal import Decimal
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from wallet.models import Account, CategoryBudget, Subcategory, Transaction, Transfer
from wallet.services import import_taxonomy


class Command(BaseCommand):
    help = "Crea 6 mesi di dati fittizi nel database demo vuoto selezionato con WALLET_DB_PATH."

    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        if (
            database["ENGINE"] != "django.db.backends.sqlite3"
            or Path(database["NAME"]).resolve()
            == (settings.BASE_DIR / "wallet.sqlite3").resolve()
        ):
            raise CommandError(
                "Seleziona un database SQLite separato con WALLET_DB_PATH. Il database personale non viene popolato."
            )
        if (
            Account.objects.exists()
            or Transaction.objects.exists()
            or Transfer.objects.exists()
            or get_user_model().objects.exists()
        ):
            raise CommandError(
                "Il database demo deve essere vuoto. Nessun dato modificato."
            )
        with transaction.atomic():
            with (settings.BASE_DIR / "wallet/categorie_movimenti.csv").open("rb") as f:
                import_taxonomy(f)
            bank = Account.objects.create(
                name="Conto principale", initial_balance=Decimal("3200.00")
            )
            card = Account.objects.create(
                name="Carta quotidiana",
                account_type="carta",
                initial_balance=Decimal("350.00"),
            )
            savings = Account.objects.create(
                name="Risparmi",
                account_type="risparmio",
                initial_balance=Decimal("5000.00"),
            )
            today = timezone.localdate()
            salary = Subcategory.objects.filter(
                kind="Entrata", name__icontains="Stipendio"
            ).first()
            expense_subs = list(
                Subcategory.objects.exclude(kind="Entrata").select_related("category")
            )
            # One subcategory per expense category, stable and reproducible.
            chosen = {s.category_id: s for s in expense_subs}
            order = 1
            for offset in range(5, -1, -1):
                index = today.year * 12 + today.month - 1 - offset
                month = date(index // 12, index % 12 + 1, 1)
                if month.replace(day=2) <= today:
                    Transaction.objects.create(
                        date=month.replace(day=2),
                        description="Stipendio · esempio",
                        amount=Decimal("2250.00"),
                        subcategory=salary,
                        account=bank,
                        order_index=order,
                    )
                    order += 1
                for position, sub in enumerate(list(chosen.values())[:13]):
                    day = 3 + (position * 2) % 24
                    when = month.replace(
                        day=min(day, calendar.monthrange(month.year, month.month)[1])
                    )
                    if when > today:
                        continue
                    amount = Decimal(25 + position * 11 + offset * 3) + Decimal("0.90")
                    Transaction.objects.create(
                        date=when,
                        description=f"{sub.name} · esempio",
                        amount=amount,
                        subcategory=sub,
                        account=card if position % 2 else bank,
                        order_index=order,
                    )
                    order += 1
                    CategoryBudget.objects.update_or_create(
                        month=month,
                        category=sub.category,
                        defaults={"amount": Decimal(70 + position * 10)},
                    )
                if month.replace(day=5) <= today:
                    Transfer.objects.create(
                        date=month.replace(day=5),
                        amount=Decimal("500"),
                        source=bank,
                        destination=card,
                        description="Ricarica carta · esempio",
                        order_index=order,
                    )
                    order += 1
                    Transfer.objects.create(
                        date=month.replace(day=5),
                        amount=Decimal("200"),
                        source=bank,
                        destination=savings,
                        description="Risparmio mensile · esempio",
                        order_index=order,
                    )
                    order += 1
            user = get_user_model().objects.create_superuser(
                username="demo", password=None
            )
            user.set_unusable_password()
            user.save(update_fields=["password"])
        self.stdout.write(
            self.style.SUCCESS(
                "Demo creata. Imposta la password con: python manage.py changepassword demo"
            )
        )
