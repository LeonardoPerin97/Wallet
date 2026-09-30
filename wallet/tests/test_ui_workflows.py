"""Financial regressions behind the interactive UI updates."""

import csv
import io
from datetime import date
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from wallet.models import (
    Account,
    Category,
    Subcategory,
    Transaction,
    Transfer,
    CategoryBudget,
)
from wallet.services.csv_wallet import import_wallet_csv


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class InteractiveWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="owner", password="test-only"
        )
        cls.a = Account.objects.create(name="Conto A")
        cls.b = Account.objects.create(name="Conto B")
        cls.category = Category.objects.create(name="Spesa")
        cls.need = Subcategory.objects.create(
            category=cls.category, name="Alimentari", kind="Uscita necessaria"
        )
        cls.extra = Subcategory.objects.create(
            category=cls.category, name="Ristoranti", kind="Uscita extra"
        )
        cls.income = Subcategory.objects.create(
            category=cls.category, name="Rimborso", kind="Entrata"
        )
        cls.investment = Subcategory.objects.create(
            category=cls.category, name="ETF", kind="Investimento"
        )

    def setUp(self):
        self.client.force_login(self.user)

    def tx(self, **values):
        return Transaction.objects.create(
            **dict(
                dict(
                    date=date(2026, 5, 5),
                    amount=D("10"),
                    account=self.a,
                    subcategory=self.need,
                ),
                **values
            )
        )

    def fields(self, sub=None, **values):
        return dict(
            dict(
                date="05/05/2026",
                amount="10,00",
                account=self.a.pk,
                category=self.category.pk,
                subcategory=(sub or self.need).pk,
            ),
            **values
        )

    def exported(self):
        response = self.client.get(
            reverse("export_csv"),
            {"periodo": "custom", "inizio": "01/05/2026", "fine": "30/06/2026"},
        )
        rows = list(
            csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";")
        )
        return {"headers": rows[0], "rows": rows[1:]}

    def test_manual_expense_override_in_both_directions_does_not_change_taxonomy(self):
        for sub, chosen in [
            (self.need, "Uscita extra"),
            (self.extra, "Uscita necessaria"),
        ]:
            with self.subTest(chosen=chosen):
                result = self.client.post(
                    reverse("transaction_new"), self.fields(sub, expense_kind=chosen)
                )
                self.assertEqual(result.status_code, 302)
                saved = Transaction.objects.get(subcategory=sub)
                self.assertEqual(saved.kind, chosen)
                self.assertEqual(saved.signed_amount, D("-10"))
                sub.refresh_from_db()
                self.assertNotEqual(sub.kind, chosen)

    def test_other_accounting_types_cannot_be_changed_to_expenses(self):
        for sub in [self.income, self.investment]:
            result = self.client.post(
                reverse("transaction_new"),
                self.fields(sub, expense_kind="Uscita extra"),
            )
            self.assertEqual(result.status_code, 200)
            self.assertIn("expense_kind", result.context["form"].errors)
            with self.assertRaises(ValidationError):
                self.tx(subcategory=sub, kind="Uscita extra")
        self.assertEqual(Transaction.objects.count(), 0)

    def test_editing_and_saving_preserve_an_expense_override(self):
        tx = self.tx(kind="Uscita extra")
        tx.description = "Descrizione aggiornata"
        tx.save()
        tx.refresh_from_db()
        self.assertEqual(tx.kind, "Uscita extra")
        page = self.client.get(reverse("transaction_edit", args=[tx.uid]))
        self.assertEqual(page.context["form"].initial["expense_kind"], "Uscita extra")
        result = self.client.post(
            reverse("transaction_edit", args=[tx.uid]),
            self.fields(expense_kind="Uscita extra", amount="20,00"),
        )
        self.assertEqual(result.status_code, 302)
        tx.refresh_from_db()
        self.assertEqual((tx.kind, tx.amount), ("Uscita extra", D("20")))

    def test_csv_roundtrip_preserves_both_transaction_and_default_kind(self):
        first = self.tx(kind="Uscita extra", order_index=1)
        second = self.tx(order_index=2)
        raw = self.exported()
        Transaction.objects.all().delete()
        Subcategory.objects.all().delete()
        Category.objects.all().delete()
        Account.objects.all().delete()
        report = import_wallet_csv(raw, commit=True)
        self.assertEqual(report["movements"], 2)
        self.assertEqual(Transaction.objects.get(uid=first.uid).kind, "Uscita extra")
        self.assertEqual(
            Transaction.objects.get(uid=second.uid).kind, "Uscita necessaria"
        )
        self.assertEqual(
            Subcategory.objects.get(name="Alimentari").kind, "Uscita necessaria"
        )
        self.assertEqual(import_wallet_csv(raw, commit=True)["duplicates"], 2)

    def test_earlier_csv_v2_without_default_type_remains_supported(self):
        saved = self.tx()
        raw = self.exported()
        raw["headers"].pop()
        for row in raw["rows"]:
            row.pop()
        saved.delete()
        self.assertEqual(import_wallet_csv(raw, commit=True)["movements"], 1)
        self.assertEqual(Transaction.objects.get().kind, "Uscita necessaria")

    def test_json_restore_keeps_the_manual_expense_kind(self):
        saved = self.tx(kind="Uscita extra")
        payload = self.client.post(reverse("backup"), {"action": "download"}).content
        saved.delete()
        result = self.client.post(
            reverse("restore_backup"),
            {
                "action": "restore",
                "confirm": "yes",
                "file": SimpleUploadedFile(
                    "wallet.json", payload, content_type="application/json"
                ),
            },
        )
        self.assertEqual(result.status_code, 302)
        self.assertEqual(Transaction.objects.get(uid=saved.uid).kind, "Uscita extra")
        self.assertEqual(
            Subcategory.objects.get(name="Alimentari").kind, "Uscita necessaria"
        )

    def test_budget_residual_consolidates_all_accounts_and_excludes_transfers(self):
        self.tx(amount=D("70"))
        self.tx(amount=D("50"), account=self.b)
        Transfer.objects.create(
            date=date(2026, 5, 5), source=self.a, destination=self.b, amount=D("100")
        )
        budget = CategoryBudget.objects.create(
            month=date(2026, 5, 1), category=self.category, amount=D("100")
        )
        context = self.client.get(reverse("budget"), {"mese": "2026-05"}).context
        self.assertEqual(
            (context["outgoing"], context["remaining"], context["remaining_label"]),
            (D("120"), D("-20"), "Sforamento"),
        )
        self.assertEqual(context["remaining_display"], D("20"))
        budget.amount = D("200")
        budget.save()
        context = self.client.get(reverse("budget"), {"mese": "2026-05"}).context
        self.assertEqual(
            (context["remaining"], context["remaining_label"]), (D("80"), "Residuo")
        )

    def test_overview_subcategory_summary_matches_bars_and_zero_month_average(self):
        self.tx(amount=D("10"))
        self.tx(amount=D("30"), subcategory=self.extra)
        self.tx(amount=D("999"), subcategory=self.income)
        query = {
            "periodo": "custom",
            "inizio": "01/05/2026",
            "fine": "30/06/2026",
            "dettaglio": "sottocategoria",
        }
        context = self.client.get(reverse("overview"), query).context
        rows = {r["name"]: r for r in context["monthly_table"]}
        self.assertEqual(set(rows), {"Spesa · Alimentari", "Spesa · Ristoranti"})
        for trace in context["charts"]["spending"]:
            self.assertEqual(rows[trace["name"]]["amount"], sum(map(D, trace["y"])))
        self.assertEqual(rows["Spesa · Ristoranti"]["average"], D("15"))
        self.assertEqual(context["donut_rows"][0]["amount"], D("40"))
