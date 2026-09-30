"""Account-selection regressions and monthly subcategory budget invariants."""

import io
import json
from datetime import date
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import QueryDict
from django.test import TestCase, override_settings
from django.urls import reverse

from wallet.forms import SubcategoryForm
from wallet.models import (
    Account,
    Category,
    CategoryBudget,
    Subcategory,
    SubcategoryBudget,
    Transaction,
    Transfer,
    UserPreference,
)
from wallet.services.filters import Filters
from wallet.services.taxonomy import import_taxonomy


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BudgetAllocationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="owner", password="test-only"
        )
        cls.a = Account.objects.create(name="Conto A", initial_balance=D(100))
        cls.b = Account.objects.create(name="Conto B")
        cls.home = Category.objects.create(name="Casa")
        cls.other = Category.objects.create(name="Altro")
        cls.rent = Subcategory.objects.create(
            category=cls.home, name="Affitto", kind="Uscita necessaria"
        )
        cls.bills = Subcategory.objects.create(
            category=cls.home, name="Bollette", kind="Uscita necessaria"
        )
        cls.extra = Subcategory.objects.create(
            category=cls.other, name="Extra", kind="Uscita extra"
        )
        cls.salary = Subcategory.objects.create(
            category=cls.other, name="Stipendio", kind="Entrata"
        )
        cls.month = date(2026, 5, 1)

    def setUp(self):
        self.client.force_login(self.user)

    def post(self, **fields):
        return self.client.post(
            reverse("budget"), {"mese": "2026-05", "azione": "salva_budget", **fields}
        )

    def split(self, first="300,10", second="100,20", **fields):
        return self.post(
            **{
                f"budget_mode_{self.home.pk}": "sottocategorie",
                f"subbudget_{self.rent.pk}": first,
                f"subbudget_{self.bills.pk}": second,
                **fields,
            }
        )

    def context(self, month="2026-05"):
        return self.client.get(reverse("budget"), {"mese": month}).context

    def restore(self, payload):
        return self.client.post(
            reverse("restore_backup"),
            {
                "action": "restore",
                "confirm": "yes",
                "file": SimpleUploadedFile("wallet.json", payload),
            },
            follow=True,
        )

    def test_no_accounts_is_empty_in_pages_csv_and_saved_preference(self):
        Transaction.objects.create(
            date=self.month, amount=D(20), account=self.a, subcategory=self.rent
        )
        Transfer.objects.create(
            date=self.month, amount=D(10), source=self.a, destination=self.b
        )
        for route in ["dashboard", "overview", "transactions"]:
            response = self.client.get(
                reverse(route), {"periodo": "tutto", "conto": ""}
            )
            self.assertEqual(response.context["selected_account_ids"], set())
            self.assertEqual(response.context["account_label"], "Nessuno")
            if route == "dashboard":
                self.assertEqual(response.context["current"], D(0))
            elif route == "overview":
                self.assertEqual(response.context["outgoing"], D(0))
            else:
                self.assertEqual(response.context["page"].paginator.count, 0)
        csv = self.client.get(reverse("export_csv"), {"conto": ""}).content.decode(
            "utf-8-sig"
        )
        self.assertEqual(len(csv.splitlines()), 1)
        self.assertTrue(UserPreference.objects.get(pk=1).no_accounts_selected)
        self.client.logout()
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(reverse("dashboard")).context["selected_account_ids"], set()
        )
        self.assertEqual(
            Filters.parse(QueryDict("conto=tutti")).account_ids, {self.a.pk, self.b.pk}
        )
        self.assertEqual(Filters.parse(QueryDict()).account_ids, {self.a.pk, self.b.pk})

    def test_subcategory_sum_spending_history_and_type_total(self):
        self.assertEqual(self.split().status_code, 302)
        self.assertFalse(CategoryBudget.objects.filter(category=self.home).exists())
        Transaction.objects.create(
            date=self.month, account=self.a, subcategory=self.rent, amount=D("200")
        )
        Transaction.objects.create(
            date=self.month, account=self.b, subcategory=self.bills, amount=D("25")
        )
        Transaction.objects.create(
            date=self.month, account=self.a, subcategory=self.salary, amount=D("1000")
        )
        Transfer.objects.create(
            date=self.month, source=self.a, destination=self.b, amount=D("500")
        )
        ctx = self.context()
        self.assertEqual(
            (ctx["total_budget"], ctx["outgoing"], ctx["remaining"]),
            (D("400.30"), D("225"), D("175.30")),
        )
        row = next(r for r in ctx["budget_rows"] if r["category"] == self.home)
        self.assertEqual(row["limit"], D("400.30"))
        self.assertEqual(
            {r["subcategory"].name: r["spent"] for r in row["subcategories"]},
            {"Affitto": D(200), "Bollette": D(25)},
        )
        self.assertEqual(sum(r["amount"] for r in ctx["type_rows"]), ctx["outgoing"])
        self.assertEqual(ctx["total_income_share_display"], "22,5%")
        later = self.context("2026-06")
        self.assertEqual(later["history"][0]["limit"], D("400.30"))
        self.assertEqual(later["history"][0]["remaining"], D("175.30"))
        self.assertEqual(later["previous_outgoing"], D(225))
        self.assertContains(
            self.client.get(reverse("budget")), '<th scope="row">TOT</th>', html=True
        )

    def test_switching_modes_has_one_total_and_preserves_unsubmitted_categories(self):
        CategoryBudget.objects.create(
            month=self.month, category=self.home, amount=D(900)
        )
        CategoryBudget.objects.create(
            month=self.month, category=self.other, amount=D(50)
        )
        self.split()
        self.assertEqual(self.context()["total_budget"], D("450.30"))
        self.post(
            **{
                f"budget_mode_{self.home.pk}": "categoria",
                f"budget_{self.home.pk}": "600,00",
            }
        )
        self.assertFalse(SubcategoryBudget.objects.exists())
        self.assertEqual(self.context()["total_budget"], D(650))

    def test_budget_months_remain_independent(self):
        CategoryBudget.objects.create(
            month=date(2026, 4, 1), category=self.home, amount=D(800)
        )
        self.split()
        self.assertEqual(self.context("2026-04")["total_budget"], D(800))
        self.assertEqual(self.context()["total_budget"], D("400.30"))
        self.assertEqual(self.context("2026-06")["total_budget"], D(0))

    def test_zero_is_a_limit_blank_removes_the_line(self):
        self.split(first="0", second="")
        self.assertEqual(SubcategoryBudget.objects.count(), 1)
        row = next(
            r for r in self.context()["budget_rows"] if r["category"] == self.home
        )
        self.assertTrue(row["has_budget"])
        self.assertTrue(row["subcategories"][0]["has_budget"])
        self.split(first="", second="")
        self.assertFalse(SubcategoryBudget.objects.exists())
        self.assertFalse(CategoryBudget.objects.exists())

    def test_invalid_partial_input_changes_nothing_and_remains_visible(self):
        self.split()
        CategoryBudget.objects.create(
            month=self.month, category=self.other, amount=D(50)
        )
        response = self.split(
            first="-25,00", second="20", **{f"budget_{self.other.pk}": "80"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="-25,00"')
        self.assertEqual(self.context()["total_budget"], D("450.30"))
        self.assertEqual(
            SubcategoryBudget.objects.get(subcategory=self.bills).amount, D("100.20")
        )
        for invalid in ["abc", "1000000000000,00", "1,2345"]:
            with self.subTest(invalid=invalid):
                response = self.split(first=invalid)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    SubcategoryBudget.objects.get(subcategory=self.rent).amount,
                    D("300.10"),
                )

    def test_archived_subcategories_keep_limits_and_spending(self):
        self.split()
        self.rent.active = False
        self.rent.save()
        self.home.active = False
        self.home.save()
        Transaction.objects.create(
            date=self.month, account=self.a, subcategory=self.rent, amount=D(20)
        )
        row = next(
            r for r in self.context()["budget_rows"] if r["category"] == self.home
        )
        self.assertEqual(row["spent"], D(20))
        self.assertEqual(row["limit"], D("400.30"))
        self.assertIn(self.rent, [r["subcategory"] for r in row["subcategories"]])

    def test_new_backup_roundtrip_and_old_backup_compatibility(self):
        old = self.client.post(reverse("backup"), {"action": "download"}).content
        self.split()
        payload = self.client.post(reverse("backup"), {"action": "download"}).content
        self.assertIn(b"wallet.subcategorybudget", payload)
        self.split(first="1", second="2")
        self.assertContains(self.restore(payload), "Backup ripristinato")
        self.assertEqual(self.context()["total_budget"], D("400.30"))
        self.assertContains(self.restore(old), "Backup ripristinato")
        self.assertFalse(SubcategoryBudget.objects.exists())

    def test_conflicting_or_invalid_backup_is_atomic(self):
        self.split()
        fixture = json.loads(
            self.client.post(reverse("backup"), {"action": "download"}).content
        )
        fixture.append(
            {
                "model": "wallet.categorybudget",
                "pk": 500,
                "fields": {
                    "month": "2026-05-01",
                    "category": self.home.pk,
                    "amount": "999",
                    "updated_at": "2026-05-01T00:00:00Z",
                },
            }
        )
        self.assertContains(
            self.restore(json.dumps(fixture).encode()), "Backup non ripristinato"
        )
        self.assertFalse(CategoryBudget.objects.exists())
        self.assertEqual(self.context()["total_budget"], D("400.30"))

    def test_budget_models_reject_incompatible_limits(self):
        for values in [
            dict(month=date(2026, 5, 2)),
            dict(amount=D(-1)),
            dict(subcategory=self.salary),
        ]:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                SubcategoryBudget.objects.create(
                    **{
                        **dict(month=self.month, subcategory=self.rent, amount=D(10)),
                        **values,
                    }
                )
        CategoryBudget.objects.create(
            month=self.month, category=self.home, amount=D(30)
        )
        with self.assertRaises(ValidationError):
            SubcategoryBudget.objects.create(
                month=self.month, subcategory=self.rent, amount=D(10)
            )
        self.split()
        with self.assertRaises(ValidationError):
            CategoryBudget.objects.create(
                month=self.month, category=self.home, amount=D(30)
            )
        with self.assertRaises(ValidationError):
            SubcategoryBudget.objects.create(
                month=self.month, subcategory=self.rent, amount=D(10)
            )

    def test_budgeted_taxonomy_cannot_change_category_or_kind(self):
        self.split()
        for changes in [dict(kind="Entrata"), dict(category=self.other.pk)]:
            form = SubcategoryForm(
                {
                    **dict(
                        category=self.home.pk,
                        name=self.rent.name,
                        kind=self.rent.kind,
                        active=True,
                        icon="tag",
                    ),
                    **changes,
                },
                instance=Subcategory.objects.get(pk=self.rent.pk),
            )
            self.assertFalse(form.is_valid())
        with self.assertRaises(ValueError):
            import_taxonomy(
                io.BytesIO(
                    b"Categoria,Sottocategoria,Colore,Tipo\nCasa,Affitto,#112233,Entrata\n"
                )
            )
        self.rent.refresh_from_db()
        self.assertEqual(self.rent.kind, "Uscita necessaria")
