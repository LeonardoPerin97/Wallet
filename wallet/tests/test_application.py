"""Acceptance tests for the revised specification, including discovered defects."""

import csv
import io
import json
from datetime import date
from decimal import Decimal as D
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.http import QueryDict
from django.db import connection
from django.test.utils import CaptureQueriesContext
from wallet.models import (
    Account,
    Category,
    Subcategory,
    Transaction,
    Transfer,
    CategoryBudget,
)
from wallet.services import balance_at, parse_money, import_taxonomy
from wallet.services.filters import Filters
from wallet.services.analytics import analytics
from wallet.forms import TransactionForm, SubcategoryForm


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ApplicationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="wallet-owner", password="test-only"
        )
        cls.a = Account.objects.create(name="Conto A", initial_balance=D("1000"))
        cls.b = Account.objects.create(name="Carta B", initial_balance=D("100"))
        cls.c = Account.objects.create(name="Risparmi C", initial_balance=D("300"))
        cls.income_cat = Category.objects.create(name="Entrate", color="#00B67A")
        cls.food_cat = Category.objects.create(name="Spesa", color="#FF9F1C")
        cls.other_cat = Category.objects.create(name="Casa", color="#7B61FF")
        cls.salary = Subcategory.objects.create(
            category=cls.income_cat, name="Stipendio", kind="Entrata"
        )
        cls.food = Subcategory.objects.create(
            category=cls.food_cat, name="Alimentari", kind="Uscita necessaria"
        )
        cls.other = Subcategory.objects.create(
            category=cls.other_cat, name="Bollette", kind="Uscita extra"
        )

    def setUp(self):
        self.client.force_login(self.user)

    def tx(
        self,
        amount="20",
        sub=None,
        account=None,
        day=date(2026, 5, 5),
        description="Esempio",
        order=1,
    ):
        return Transaction.objects.create(
            date=day,
            amount=D(amount),
            subcategory=sub or self.food,
            account=account or self.a,
            description=description,
            order_index=order,
        )

    def transfer(
        self, amount="100", source=None, destination=None, day=date(2026, 5, 5), order=2
    ):
        return Transfer.objects.create(
            date=day,
            amount=D(amount),
            source=source or self.a,
            destination=destination or self.b,
            order_index=order,
        )

    def params(self, **kw):
        return {"inizio": "01/05/2026", "fine": "31/05/2026", "periodo": "custom", **kw}

    def filters(self, **kw):
        q = QueryDict("", mutable=True)
        for k, v in self.params(**kw).items():
            q.setlist(k, v if isinstance(v, list) else [str(v)])
        return Filters.parse(q)

    def test_five_pages_have_separate_responsibilities_and_navigation(self):
        for route, title in [
            ("dashboard", "Dashboard"),
            ("overview", "Overview"),
            ("transactions", "Movimenti"),
            ("budget", "Budget mensile"),
            ("settings", "Account e impostazioni"),
        ]:
            response = self.client.get(reverse(route))
            self.assertContains(response, title)
            self.assertContains(response, "Navigazione mobile")
            self.assertNotContains(response, "nav-more")
        self.assertNotContains(
            self.client.get(reverse("dashboard")), "Uscite per categoria"
        )
        self.assertNotContains(self.client.get(reverse("overview")), "Saldo attuale")

    def test_all_account_register_contains_two_linked_transfer_legs(self):
        t = self.transfer()
        page = self.client.get(reverse("transactions"), self.params()).context["page"]
        self.assertEqual(len(page.object_list), 2)
        self.assertEqual({r.uid for r in page}, {t.uid})
        self.assertEqual(sum((r.signed_amount for r in page), D(0)), D(0))
        self.assertEqual({r.balance_after for r in page}, {D(900), D(200)})

    def test_multi_account_perimeter_counts_only_boundary_transfers(self):
        self.tx("10")
        self.transfer("100")
        self.transfer("15", source=self.c, destination=self.a, order=3)
        self.transfer("8", source=self.b, destination=self.c, order=4)
        response = self.client.get(
            reverse("dashboard"), self.params(conto=[self.a.id, self.b.id])
        )
        ctx = response.context
        self.assertEqual(
            (ctx["income"], ctx["outgoing"], ctx["net"]), (D(15), D(18), D(-3))
        )
        self.assertEqual(ctx["closing"] - ctx["opening"], ctx["net"])
        for mode in ("totale", "tipo", "categoria"):
            incoming = sum(
                (
                    D(y)
                    for trace in ctx["charts"]["flows"][mode]
                    if trace.get("offsetgroup") == "income"
                    for y in trace["y"]
                ),
                D(0),
            )
            outgoing = sum(
                (
                    D(y)
                    for trace in ctx["charts"]["flows"][mode]
                    if trace.get("offsetgroup") == "outgoing"
                    for y in trace["y"]
                ),
                D(0),
            )
            self.assertEqual((incoming, outgoing), (D(15), D(18)))

    def test_consolidated_analytics_excludes_internal_transfers(self):
        self.tx()
        self.transfer()
        home = self.client.get(reverse("dashboard"), self.params()).context
        dashboard = self.client.get(reverse("overview"), self.params()).context
        self.assertEqual(home["outgoing"], D(20))
        self.assertEqual(home["transfers_out"], D(0))
        self.assertNotIn("Giroconto", [r["name"] for r in dashboard["donut_rows"]])

    def test_donut_boundary_transfer_is_its_own_category(self):
        self.tx()
        self.transfer()
        ctx = self.client.get(reverse("overview"), self.params(conto=self.a.id)).context
        rows = {r["name"]: r for r in ctx["donut_rows"]}
        self.assertEqual(rows["Giroconto"]["amount"], D(100))
        self.assertEqual(ctx["donut_total"], D(120))
        self.assertEqual(rows["Giroconto"]["count"], 1)
        self.assertEqual(sum((r["percent"] for r in rows.values()), D(0)), D(100))

    def test_category_and_subcategory_filters_apply_to_all_analytics(self):
        self.tx()
        self.tx("30", sub=self.other)
        self.transfer()
        ctx = self.client.get(
            reverse("overview"),
            self.params(
                conto=self.a.id, categoria=self.food_cat.id, sottocategoria=self.food.id
            ),
        ).context
        self.assertEqual(ctx["outgoing"], D(20))
        self.assertEqual([r["name"] for r in ctx["monthly_table"]], ["Spesa"])
        self.assertEqual(
            sum(D(y) for t in ctx["charts"]["spending"] for y in t["y"]), D(20)
        )

    def test_home_ignores_category_filters_to_keep_balances_reconciled(self):
        self.tx()
        self.tx("30", sub=self.other)
        self.transfer()
        ctx = self.client.get(
            reverse("dashboard"),
            self.params(conto=self.a.id, categoria=self.food_cat.id, tipo="Entrata"),
        ).context
        self.assertEqual(ctx["outgoing"], D(150))
        self.assertEqual(ctx["closing"] - ctx["opening"], D(-150))

    def test_empty_account_selection_stays_empty(self):
        self.tx()
        ctx = self.client.get(reverse("dashboard"), self.params(conto="")).context
        self.assertEqual(ctx["selected_account_ids"], set())
        self.assertEqual(ctx["closing"], D(0))

    def test_archived_accounts_remain_selectable_in_history(self):
        self.b.active = False
        self.b.save()
        self.tx("40", sub=self.salary, account=self.b)
        ctx = self.client.get(
            reverse("dashboard"), self.params(conto=self.b.id)
        ).context
        self.assertEqual(ctx["closing"], D(140))
        self.assertNotIn(self.b, list(TransactionForm().fields["account"].queryset))

    def test_three_month_range_handles_end_of_month_and_leap_year(self):
        with patch(
            "wallet.services.filters.timezone.localdate", return_value=date(2024, 5, 31)
        ):
            f = self.filters(periodo="3m")
            self.assertEqual(f.start, date(2024, 2, 29))
            self.assertEqual(f.end, date(2024, 5, 31))

    def test_all_period_discards_old_dates_and_excludes_future_operations(self):
        self.tx("20", day=date(2026, 5, 5))
        self.transfer(day=date(2026, 4, 2))
        self.tx("999", day=date(2026, 7, 1))
        with patch(
            "wallet.services.filters.timezone.localdate", return_value=date(2026, 6, 10)
        ):
            for route in ("dashboard", "overview", "transactions"):
                with self.subTest(route=route):
                    ctx = self.client.get(
                        reverse(route), self.params(periodo="tutto")
                    ).context
                    self.assertEqual(
                        (ctx["start"], ctx["end"]), ("2026-04-02", "2026-06-10")
                    )
                    if route == "dashboard":
                        self.assertEqual(ctx["outgoing"], D(20))
                    if route == "transactions":
                        self.assertEqual(ctx["page"].paginator.count, 3)

    def test_all_period_saved_in_session_advances_to_today(self):
        self.tx(day=date(2026, 5, 5))
        with patch(
            "wallet.services.filters.timezone.localdate", return_value=date(2026, 6, 10)
        ):
            self.client.get(reverse("dashboard"), self.params(periodo="tutto"))
        with patch(
            "wallet.services.filters.timezone.localdate", return_value=date(2026, 6, 11)
        ):
            ctx = self.client.get(reverse("dashboard")).context
        self.assertEqual((ctx["start"], ctx["end"]), ("2026-05-05", "2026-06-11"))

    def test_explicit_dates_override_previously_saved_all_period(self):
        self.tx(day=date(2026, 5, 5))
        for route in ("dashboard", "overview"):
            with self.subTest(route=route):
                self.client.get(reverse(route), {"periodo": "tutto", "conto": "tutti"})
                ctx = self.client.get(
                    reverse(route), {"inizio": "01/05/2026", "fine": "31/05/2026"}
                ).context
                self.assertEqual(ctx["period"], "custom")
                self.assertEqual(
                    (ctx["start"], ctx["end"]), ("2026-05-01", "2026-05-31")
                )

    def test_current_balance_is_independent_of_period_end(self):
        self.tx("20", day=date(2026, 5, 5))
        self.tx("30", day=date(2026, 6, 5))
        with patch(
            "wallet.services.filters.timezone.localdate", return_value=date(2026, 6, 10)
        ):
            ctx = self.client.get(reverse("dashboard"), self.params()).context
        self.assertEqual(ctx["current"], D(1350))
        self.assertEqual(ctx["closing"], D(1380))

    def test_daily_series_includes_empty_days_and_opening_before_period(self):
        self.tx("50", day=date(2026, 4, 30))
        self.tx("20", day=date(2026, 5, 2))
        ctx = self.client.get(
            reverse("dashboard"), self.params(inizio="01/05/2026", fine="03/05/2026")
        ).context
        series = ctx["charts"]["daily"][0]
        self.assertEqual(series["x"], ["2026-05-01", "2026-05-02", "2026-05-03"])
        self.assertEqual([D(y) for y in series["y"]], [D(1350), D(1330), D(1330)])

    def test_monthly_average_includes_zero_months_and_partial_months(self):
        self.tx("20", day=date(2026, 1, 31))
        self.tx("40", day=date(2026, 4, 1))
        ctx = self.client.get(
            reverse("overview"), {"inizio": "31/01/2026", "fine": "01/04/2026"}
        ).context
        self.assertEqual(ctx["month_count"], 4)
        self.assertEqual(ctx["monthly_table"][0]["average"], D(15))
        self.assertEqual(
            [D(v) for v in ctx["charts"]["spending"][0]["y"]],
            [D(20), D(0), D(0), D(40)],
        )

    def test_month_picker_changes_all_dashboard_charts(self):
        self.tx("20", day=date(2026, 4, 2))
        self.tx("40")
        ctx = self.client.get(reverse("overview"), {"periodo": "mese:2026-05"}).context
        self.assertEqual((ctx["start"], ctx["end"]), ("2026-05-01", "2026-05-31"))
        self.assertEqual(ctx["outgoing"], D(40))
        self.assertEqual(ctx["month_count"], 1)

    def test_filter_preferences_survive_sorting_without_freezing_relative_dates(self):
        self.client.get(
            reverse("overview"),
            self.params(conto=self.b.id, categoria=self.food_cat.id),
        )
        later = self.client.get(reverse("overview"), {"ordine": "name"}).context
        self.assertEqual(later["selected_account_ids"], {self.b.id})
        self.assertEqual(later["selected_category_ids"], {self.food_cat.id})
        with patch(
            "wallet.services.filters.timezone.localdate", return_value=date(2026, 7, 31)
        ):
            self.client.get(reverse("dashboard"), {"periodo": "1m", "conto": "tutti"})
        with patch(
            "wallet.services.filters.timezone.localdate", return_value=date(2026, 8, 1)
        ):
            later = self.client.get(reverse("dashboard")).context
        self.assertEqual(later["start"], "2026-07-01")

    def test_pagination_all_and_csv_use_identical_filters(self):
        Transaction.objects.bulk_create(
            [
                Transaction(
                    date=date(2026, 5, 5),
                    amount=D(i + 1),
                    subcategory=self.food,
                    kind=self.food.kind,
                    account=self.a,
                    description=f"Test {i}",
                )
                for i in range(103)
            ]
        )
        query = self.params(conto=self.a.id, per_pagina="50")
        page = self.client.get(reverse("transactions"), query).context["page"]
        self.assertEqual(len(page), 50)
        self.assertEqual(page.paginator.num_pages, 3)
        rows = list(
            csv.reader(
                io.StringIO(
                    self.client.get(reverse("export_csv"), query).content.decode(
                        "utf-8-sig"
                    )
                ),
                delimiter=";",
            )
        )
        self.assertEqual(len(rows), 104)
        self.assertEqual(
            len(
                self.client.get(
                    reverse("transactions"), {**query, "per_pagina": "tutti"}
                ).context["page"]
            ),
            103,
        )

    def test_list_month_totals_include_full_filtered_month_not_just_page(self):
        self.tx("20")
        self.tx("100", sub=self.salary)
        self.transfer("30")
        page = self.client.get(reverse("transactions"), self.params(vista="lista"))
        month = page.context["grouped_months"][0]
        self.assertEqual(
            (month["income"], month["outgoing"], month["net"]), (D(130), D(50), D(80))
        )
        self.assertNotContains(page, "row-actions")
        self.assertEqual(month["days"][0]["net"], D(80))

    def test_invalid_form_category_does_not_raise_or_save(self):
        r = self.client.post(
            reverse("transaction_new"),
            {
                "date": "05/05/2026",
                "amount": "10",
                "category": "bad",
                "subcategory": self.food.id,
                "account": self.a.id,
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_editing_transaction_can_change_category_and_subcategory(self):
        t = self.tx()
        r = self.client.post(
            reverse("transaction_edit", args=[t.uid]),
            {
                "date": "05/05/2026",
                "amount": "12,50",
                "category": self.other_cat.id,
                "subcategory": self.other.id,
                "account": self.a.id,
            },
        )
        self.assertEqual(r.status_code, 302)
        t.refresh_from_db()
        self.assertEqual(t.subcategory_id, self.other.id)
        self.assertEqual(t.amount, D("12.50"))

    def test_income_flow_cannot_save_an_expense_category(self):
        r = self.client.post(
            reverse("transaction_new"),
            {
                "flusso": "entrata",
                "date": "05/05/2026",
                "amount": "10",
                "category": self.food_cat.id,
                "subcategory": self.food.id,
                "account": self.a.id,
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Transaction.objects.exists())

    def test_same_account_transfer_is_rejected_without_changing_balances(self):
        r = self.client.post(
            reverse("transfers"),
            {
                "date": "05/05/2026",
                "amount": "10",
                "source": self.a.id,
                "destination": self.a.id,
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Transfer.objects.exists())
        self.assertEqual(balance_at(date(2026, 5, 5), {self.a.id}), D(1000))

    def test_account_edit_preserves_history_and_type(self):
        t = self.tx()
        r = self.client.post(
            reverse("settings"),
            {
                "account_id": self.a.id,
                "name": "Nuovo nome",
                "account_type": "carta",
                "initial_balance": "1.000,00",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.a.refresh_from_db()
        self.assertFalse(self.a.active)
        self.assertEqual(self.a.account_type, "carta")
        self.assertTrue(Transaction.objects.filter(pk=t.pk).exists())

    def test_used_taxonomy_kind_cannot_rewrite_historical_sign(self):
        t = self.tx()
        form = SubcategoryForm(
            {
                "category": self.food_cat.id,
                "name": "Alimentari",
                "kind": "Entrata",
                "icon": "tag",
                "active": "on",
            },
            instance=self.food,
        )
        self.assertFalse(form.is_valid())
        data = (
            b"Categoria,Sottocategoria,Colore,Tipo\nSpesa,Alimentari,#00B67A,Entrata\n"
        )
        with self.assertRaises(ValueError):
            import_taxonomy(io.BytesIO(data))
        t.refresh_from_db()
        self.assertEqual(t.signed_amount, D(-20))

    def test_budget_includes_archived_spending_and_zero_limit_overrun(self):
        self.tx()
        self.transfer()
        self.food_cat.active = False
        self.food_cat.save()
        CategoryBudget.objects.create(
            month=date(2026, 5, 1), category=self.food_cat, amount=D(0)
        )
        ctx = self.client.get(reverse("budget"), {"mese": "2026-05"}).context
        self.assertEqual(ctx["outgoing"], D(20))
        row = next(r for r in ctx["budget_rows"] if r["category"] == self.food_cat)
        self.assertEqual(row["state"], "over")
        self.assertEqual(row["remaining"], D(-20))

    def test_budget_history_covers_twelve_months_and_excludes_transfers(self):
        self.tx()
        self.transfer()
        CategoryBudget.objects.create(
            month=date(2026, 5, 1), category=self.food_cat, amount=D(100)
        )
        history = self.client.get(reverse("budget"), {"mese": "2026-06"}).context[
            "history"
        ]
        self.assertEqual(len(history), 12)
        self.assertEqual(history[0]["spent"], D(20))
        self.assertEqual(history[0]["remaining"], D(80))

    def test_restore_with_existing_budgets_succeeds(self):
        self.tx()
        CategoryBudget.objects.create(
            month=date(2026, 5, 1), category=self.food_cat, amount=D(200)
        )
        backup = self.client.post(reverse("backup"), {"action": "download"}).content
        self.tx("30")
        CategoryBudget.objects.update(amount=D(300))
        r = self.client.post(
            reverse("restore_backup"),
            {
                "action": "restore",
                "confirm": "yes",
                "file": SimpleUploadedFile("copy.json", backup),
            },
            follow=True,
        )
        self.assertContains(r, "Backup ripristinato")
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(CategoryBudget.objects.get().amount, D(200))
        self.assertNotIn(b"auth.user", backup)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_invalid_restore_is_atomic(self):
        self.tx()
        before = balance_at(date(2026, 5, 31))
        fixture = json.loads(
            self.client.post(reverse("backup"), {"action": "download"}).content
        )
        next(row for row in fixture if row["model"] == "wallet.transaction")["fields"][
            "amount"
        ] = "-10"
        self.client.post(
            reverse("restore_backup"),
            {
                "action": "restore",
                "confirm": "yes",
                "file": SimpleUploadedFile(
                    "invalid.json", json.dumps(fixture).encode()
                ),
            },
        )
        self.assertEqual(balance_at(date(2026, 5, 31)), before)

    def test_import_invalid_rows_block_entire_confirmation_and_keep_review(self):
        session = self.client.session
        base = {
            "row": 0,
            "date": "2026-05-05",
            "amount": "10",
            "description": "",
            "account_name": self.a.name,
            "subcategory_id": self.food.id,
            "operation_time": "",
            "external_id": "",
            "balance": "",
            "errors": [],
            "warnings": [],
            "status": "ok",
        }
        session["wallet_import_rows"] = [base, {**base, "row": 1, "date": "invalid"}]
        session.save()
        self.client.post(reverse("import_confirm"), {"confirm": "yes"})
        self.assertFalse(Transaction.objects.exists())
        self.assertEqual(len(self.client.session["wallet_import_rows"]), 2)
        self.assertEqual(self.client.get(reverse("import")).status_code, 200)
        r = self.client.post(
            reverse("import_confirm"), {"confirm": "yes", "date_1": "06/05/2026"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Transaction.objects.count(), 2)

    def test_import_review_sparse_balances_and_constant_query_count(self):
        from wallet.services.importing import import_review_context

        rows = [
            dict(
                row=i,
                date="2026-05-05",
                amount="10",
                description="",
                account_name=self.a.name,
                subcategory_id=self.food.id,
                operation_time="",
                balance="",
                status="ok",
            )
            for i in range(100)
        ]
        rows[1]["balance"] = "980.00"
        rows[-1]["balance"] = "0.00"
        with self.assertNumQueries(2):
            context = import_review_context(rows, {"balance": "0"})
        check = context["balance_checks"][self.a.name]
        self.assertEqual(check["opening"], D("1000"))
        self.assertTrue(check["consistent"])
        self.assertTrue(check["matches_existing"])
        self.assertTrue(context["has_balance"])

    def test_import_external_id_duplicate_ignores_changed_notes(self):
        existing = self.tx()
        existing.external_id = "bank-id-100"
        existing.save()
        session = self.client.session
        session["wallet_import_rows"] = [
            dict(
                row=0,
                date="2026-05-05",
                amount="20",
                description="Esempio",
                account_name=self.a.name,
                subcategory_id=self.food.id,
                operation_time="",
                external_id=existing.external_id,
                notes="Una nota aggiunta al secondo file",
                balance="",
                status="duplicato",
                errors=[],
                warnings=[],
            )
        ]
        session.save()
        response = self.client.post(reverse("import_confirm"), {"confirm": "yes"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["duplicates"], 1)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_malformed_money_is_rejected_instead_of_sanitized(self):
        for v in ["10abc", "NaN", "1e3", "9999999999999", "1.234,567"]:
            with self.assertRaises(ValueError):
                parse_money(v)

    def test_csv_text_cells_cannot_inject_spreadsheet_formulas(self):
        self.tx(description='=HYPERLINK("https://example.com")')
        data = self.client.get(reverse("export_csv"), self.params()).content.decode(
            "utf-8-sig"
        )
        rows = list(csv.reader(io.StringIO(data), delimiter=";"))
        self.assertTrue(rows[1][1].startswith("'="))

    def test_untrusted_labels_are_json_escaped(self):
        self.food_cat.name = "</script><script>alert(1)</script>"
        self.food_cat.save()
        self.tx()
        r = self.client.get(reverse("overview"), self.params())
        self.assertNotContains(r, "<script>alert(1)</script>")
        self.assertContains(r, "\\u003C/script\\u003E")

    def test_dashboard_query_count_does_not_grow_with_transaction_rows(self):
        self.tx()
        with CaptureQueriesContext(connection) as first:
            analytics(self.filters(), with_balance=True)
        Transaction.objects.bulk_create(
            [
                Transaction(
                    date=date(2026, 5, 5),
                    amount=D(1),
                    subcategory=self.food,
                    kind=self.food.kind,
                    account=self.a,
                )
                for _ in range(100)
            ]
        )
        with CaptureQueriesContext(connection) as later:
            analytics(self.filters(), with_balance=True)
        self.assertLessEqual(len(later), len(first) + 1)
        self.assertLess(len(later), 20)

    def test_csrf_is_required_for_mutations(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("transaction_new"), {}).status_code, 403)

    def test_new_endpoints_are_private(self):
        self.client.logout()
        for route in [
            "dashboard",
            "overview",
            "settings",
            "overview_expense_data",
            "export_csv",
        ]:
            self.assertEqual(self.client.get(reverse(route)).status_code, 302)
