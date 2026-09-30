from datetime import date, timedelta
from decimal import Decimal
import csv
import json
from pathlib import Path
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ..models import (
    Account,
    Category,
    CategoryBudget,
    Subcategory,
    Transaction,
    Transfer,
)
from ..services import (
    balance_at,
    balances_after_transactions,
    month_starts,
    parse_date,
    parse_money,
)
from ..services import import_taxonomy


class LedgerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="wallet-owner", password="password-test-sicura-1"
        )
        self.client.force_login(self.user)
        self.income_cat = Category.objects.create(name="Entrate", color="#16A34A")
        self.supermarket_cat = Category.objects.create(
            name="Supermercati", color="#EA580C"
        )
        self.eating_out_cat = Category.objects.create(
            name="Bar, ristoranti e delivery", color="#EA580C"
        )
        self.save_cat = Category.objects.create(
            name="Risparmio e investimenti", color="#0F766E"
        )
        self.salary = Subcategory.objects.create(
            category=self.income_cat, name="Stipendio", kind="Entrata"
        )
        self.necessary = Subcategory.objects.create(
            category=self.supermarket_cat, name="Supermercato", kind="Uscita necessaria"
        )
        self.extra = Subcategory.objects.create(
            category=self.eating_out_cat, name="Bar", kind="Uscita extra"
        )
        self.invest = Subcategory.objects.create(
            category=self.save_cat, name="ETF", kind="Investimento"
        )
        self.a = Account.objects.create(
            name="Carta", initial_balance=Decimal("1000.00")
        )
        self.b = Account.objects.create(name="Conto", initial_balance=Decimal("0.00"))

    def tx(self, day, sub, amount, order, account=None, description="Test"):
        return Transaction.objects.create(
            date=day,
            subcategory=sub,
            kind=sub.kind,
            amount=Decimal(amount),
            order_index=order,
            account=account or self.a,
            description=description,
        )

    def test_each_taxonomy_type_applies_its_expected_sign(self):
        day = date(2026, 1, 1)
        self.tx(day, self.salary, "100.00", 1)
        self.tx(day, self.necessary, "10.00", 2)
        self.tx(day, self.extra, "5.00", 3)
        self.tx(day, self.invest, "20.00", 4)
        self.assertEqual(balance_at(day, {self.a.id}), Decimal("1065.00"))
        self.assertEqual(
            sum((t.signed_amount for t in Transaction.objects.all()), Decimal("0")),
            Decimal("65.00"),
        )

    def test_same_day_order_and_balance_after_each_transaction(self):
        day = date(2026, 2, 10)
        first = self.tx(day, self.salary, "50.00", 10, description="Stipendio")
        second = self.tx(day, self.necessary, "20.00", 11, description="Spesa")
        Transfer.objects.create(
            date=day,
            order_index=12,
            source=self.a,
            destination=self.b,
            amount=Decimal("30.00"),
        )
        third = self.tx(day, self.invest, "5.00", 13, description="PAC")
        running = balances_after_transactions(self.a.id)
        self.assertEqual(running[first.id], Decimal("1050.00"))
        self.assertEqual(running[second.id], Decimal("1030.00"))
        self.assertEqual(running[third.id], Decimal("995.00"))
        self.assertEqual(balance_at(day, {self.a.id}), Decimal("995.00"))
        self.assertEqual(
            balance_at(day), Decimal("1025.00")
        )  # Consolidated transfer cancels out.

    def test_inclusive_period_and_net_matches_consolidated_balance_change(self):
        self.tx(date(2026, 3, 1), self.salary, "80.00", 1)
        self.tx(date(2026, 3, 31), self.necessary, "30.00", 2)
        self.tx(date(2026, 4, 1), self.extra, "9.00", 3)
        response = self.client.get(
            reverse("dashboard"), {"inizio": "2026-03-01", "fine": "2026-03-31"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["income"], Decimal("80.00"))
        self.assertEqual(response.context["outgoing"], Decimal("30.00"))
        self.assertEqual(response.context["net"], Decimal("50.00"))
        self.assertEqual(
            response.context["closing"] - response.context["opening"], Decimal("50.00")
        )
        self.assertEqual(response.context["transaction_count"], 2)

    def test_dashboard_filter_preferences_survive_a_later_visit(self):
        query = {
            "inizio": "2026-03-01",
            "fine": "2026-03-31",
            "conto": str(self.a.id),
            "periodo": "manuale",
        }
        first = self.client.get(reverse("dashboard"), query)
        self.assertEqual(first.context["selected_account"], self.a.id)
        later = self.client.get(reverse("dashboard"))
        self.assertEqual(later.context["selected_account"], self.a.id)
        self.assertEqual(later.context["start"], "2026-03-01")
        self.assertEqual(later.context["end"], "2026-03-31")

    def test_dashboard_filters_accounts_but_ignores_legacy_category_filter(self):
        self.tx(date(2026, 3, 2), self.salary, "100.00", 1, account=self.a)
        self.tx(date(2026, 3, 3), self.necessary, "20.00", 2, account=self.a)
        self.tx(date(2026, 3, 4), self.extra, "10.00", 3, account=self.b)
        query = {
            "inizio": "2026-03-01",
            "fine": "2026-03-31",
            "periodo": "manuale",
            "conto": [str(self.a.id), str(self.b.id)],
            "categoria": [str(self.supermarket_cat.id)],
        }
        response = self.client.get(reverse("dashboard"), query)
        self.assertEqual(
            response.context["selected_account_ids"], {self.a.id, self.b.id}
        )
        self.assertEqual(
            response.context["selected_category_ids"],
            {
                self.income_cat.id,
                self.supermarket_cat.id,
                self.eating_out_cat.id,
                self.save_cat.id,
            },
        )
        self.assertEqual(response.context["income"], Decimal("100.00"))
        self.assertEqual(response.context["outgoing"], Decimal("30.00"))
        self.assertNotContains(response, 'data-filter-panel="dashboard-categories"')
        later = self.client.get(reverse("dashboard"))
        self.assertEqual(later.context["selected_account_ids"], {self.a.id, self.b.id})
        self.assertEqual(
            later.context["selected_category_ids"],
            {
                self.income_cat.id,
                self.supermarket_cat.id,
                self.eating_out_cat.id,
                self.save_cat.id,
            },
        )

    @override_settings(WALLET_OWNER_USERNAME="wallet-owner")
    def test_only_configured_owner_can_authenticate_or_keep_a_session(self):
        User = get_user_model()
        regular_user = User.objects.create_user(
            username="reader", password="password-reader-sicura-1"
        )
        other_admin = User.objects.create_superuser(
            username="other-admin", password="password-admin-sicura-1"
        )
        self.client.logout()

        response = self.client.post(
            reverse("login"),
            {
                "username": regular_user.username,
                "password": "password-reader-sicura-1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].errors.as_data()["__all__"][0].code,
            "wallet_owner_required",
        )
        self.assertNotIn("_auth_user_id", self.client.session)

        response = self.client.post(
            reverse("login"),
            {
                "username": other_admin.username,
                "password": "password-admin-sicura-1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].errors.as_data()["__all__"][0].code,
            "wallet_owner_required",
        )
        self.assertNotIn("_auth_user_id", self.client.session)

        self.client.force_login(regular_user)
        response = self.client.get(reverse("transactions"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)

        response = self.client.post(
            reverse("login"),
            {
                "username": self.user.username,
                "password": "password-test-sicura-1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))

    def test_month_window_includes_empty_months_and_decimal_import_formats(self):
        self.assertEqual(
            month_starts(date(2026, 1, 31), date(2026, 4, 1)),
            [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)],
        )
        self.assertEqual(parse_money("1.234,56 €"), Decimal("1234.56"))
        self.assertEqual(parse_money("1.234.567"), Decimal("1234567"))
        self.assertEqual(parse_money("1.234"), Decimal("1234"))
        self.assertEqual(parse_money("-98,70"), Decimal("-98.70"))
        self.assertEqual(parse_money("1,234.56"), Decimal("1234.56"))
        self.assertEqual(parse_date("24/09/2026"), date(2026, 9, 24))

    def test_invalid_amount_and_unknown_import_values_are_explicit(self):
        with self.assertRaises(ValueError):
            parse_money("non leggibile")
        with self.assertRaises(ValueError):
            parse_date("31/31/2026")

    def test_manual_form_keeps_category_subcategory_and_type_consistent(self):
        response = self.client.post(
            reverse("transaction_new"),
            {
                "date": "2026-09-24",
                "operation_time": "08:15",
                "description": "Spesa manuale",
                "amount": "12.50",
                "account": self.a.id,
                "category": self.supermarket_cat.id,
                "subcategory": self.necessary.id,
                "notes": "",
                "external_id": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        tx = Transaction.objects.get(description="Spesa manuale")
        self.assertEqual(tx.kind, "Uscita necessaria")
        self.assertEqual(tx.signed_amount, Decimal("-12.50"))
        self.assertEqual(tx.operation_time.strftime("%H:%M"), "08:15")
        edit_page = self.client.get(reverse("transaction_edit", args=[tx.uid]))
        self.assertEqual(edit_page.status_code, 200)
        self.assertEqual(
            edit_page.context["form"].initial["subcategory"], self.necessary.id
        )
        self.assertEqual(
            edit_page.context["form"].initial["category"], self.supermarket_cat.id
        )

    def test_new_movement_defaults_to_today_and_allows_blank_description(self):
        response = self.client.get(
            reverse("transaction_new"), {"conto": str(self.a.id)}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            str(response.context["form"]["date"].value()),
            timezone.localdate().isoformat(),
        )
        self.assertContains(
            response, f'name="date" value="{timezone.localdate():%d/%m/%Y}"'
        )
        self.assertEqual(
            str(response.context["form"]["account"].value()), str(self.a.id)
        )
        self.assertFalse(response.context["form"]["description"].field.required)
        self.assertNotIn("notes", response.context["form"].fields)
        self.assertContains(response, "id_category")
        self.assertContains(response, "id_subcategory")
        self.assertIn(
            self.supermarket_cat, response.context["form"].fields["category"].queryset
        )

        self.assertNotContains(response, "Scegli una categoria")
        self.assertNotContains(response, ">Note<")
        response = self.client.post(
            reverse("transaction_new"),
            {
                "date": timezone.localdate().isoformat(),
                "operation_time": "",
                "description": "",
                "amount": "8.25",
                "account": self.a.id,
                "category": self.supermarket_cat.id,
                "subcategory": self.necessary.id,
                "notes": "",
                "external_id": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Transaction.objects.filter(description="", amount=Decimal("8.25")).exists()
        )

    def test_budget_month_saves_category_limits_and_excludes_internal_transfers(self):
        month = date(2026, 3, 1)
        self.tx(date(2026, 3, 2), self.salary, "1000.00", 1)
        self.tx(date(2026, 3, 4), self.necessary, "150.00", 2)
        self.tx(date(2026, 3, 8), self.extra, "50.00", 3)
        self.tx(date(2026, 3, 9), self.invest, "100.00", 4)
        Transfer.objects.create(
            date=date(2026, 3, 10),
            source=self.a,
            destination=self.b,
            amount=Decimal("40.00"),
        )
        response = self.client.post(
            reverse("budget"),
            {
                "mese": "2026-03",
                "azione": "salva_budget",
                f"budget_{self.supermarket_cat.id}": "200,00",
                f"budget_{self.eating_out_cat.id}": "100,00",
                f"budget_{self.save_cat.id}": "150,00",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CategoryBudget.objects.filter(month=month).count(), 3)
        page = self.client.get(reverse("budget"), {"mese": "2026-03"})
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["income"], Decimal("1000.00"))
        self.assertEqual(page.context["outgoing"], Decimal("300.00"))
        self.assertEqual(page.context["net"], Decimal("700.00"))
        self.assertEqual(page.context["total_budget"], Decimal("450.00"))
        self.assertEqual(page.context["previous_outgoing"], Decimal("0.00"))
        self.assertContains(page, "Il tuo piano per")
        self.assertNotContains(page, "Giroconto</strong>")

    def test_budget_rejects_negative_amounts_and_keeps_the_value_visible_for_correction(
        self,
    ):
        response = self.client.post(
            reverse("budget"),
            {
                "mese": "2026-03",
                "azione": "salva_budget",
                f"budget_{self.supermarket_cat.id}": "-25,00",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CategoryBudget.objects.exists())
        self.assertContains(response, "inserisci un importo pari o superiore a zero")
        self.assertContains(response, 'value="-25,00"')

    def test_categories_page_shows_taxonomy_and_offers_csv_import(self):
        settings = self.client.get(reverse("settings"))
        self.assertEqual(settings.status_code, 200)
        self.assertNotContains(settings, "Importa CSV categorie")
        self.assertNotContains(settings, "taxonomy_import")
        categories = self.client.get(reverse("categories"))
        self.assertEqual(categories.status_code, 200)
        self.assertContains(categories, "Supermercati")
        self.assertContains(categories, "Uscita necessaria")
        self.assertContains(categories, 'type="file"')
        self.assertContains(categories, "Importa categorie")
        self.assertEqual(
            self.client.post("/configurazione/tassonomia/").status_code, 404
        )

    def test_static_stylesheet_url_is_root_relative_on_nested_pages(self):
        response = self.client.get(reverse("categories"))
        self.assertContains(response, 'href="/static/wallet/app.css"')

    def test_filter_date_inputs_display_italian_dates_and_accept_them(self):
        movement = self.tx(date(2026, 3, 5), self.necessary, "20.00", 1)
        dashboard = self.client.get(
            reverse("dashboard"), {"inizio": "01/03/2026", "fine": "31/03/2026"}
        )
        self.assertEqual(dashboard.context["transaction_count"], 1)
        self.assertContains(dashboard, 'placeholder="gg/mm/aaaa"')
        self.assertContains(dashboard, 'value="01/03/2026"')
        movements = self.client.get(
            reverse("transactions"), {"inizio": "01/03/2026", "fine": "31/03/2026"}
        )
        self.assertEqual(movements.context["page"].object_list[0].id, movement.id)
        self.assertContains(movements, 'value="01/03/2026"')

    def test_movement_filters_accept_multiple_categories_subcategories_types_and_accounts(
        self,
    ):
        day = date(2026, 4, 8)
        salary = self.tx(
            day, self.salary, "100.00", 1, account=self.a, description="Accredito"
        )
        supermarket = self.tx(
            day, self.necessary, "25.00", 2, account=self.b, description="Spesa"
        )
        self.tx(day, self.extra, "15.00", 3, account=self.b, description="Ristorante")
        self.tx(day, self.invest, "10.00", 4, account=self.a, description="PAC")

        response = self.client.get(
            reverse("transactions"),
            {
                "categoria": [str(self.income_cat.id), str(self.supermarket_cat.id)],
                "sottocategoria": [str(self.salary.id), str(self.necessary.id)],
                "tipo": ["Entrata", "Uscita necessaria"],
                "conto": [str(self.a.id), str(self.b.id)],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {row.id for row in response.context["page"].object_list},
            {salary.id, supermarket.id},
        )
        self.assertEqual(
            response.context["selected_category_ids"],
            {self.income_cat.id, self.supermarket_cat.id},
        )
        self.assertEqual(
            response.context["selected_subcategory_ids"],
            {self.salary.id, self.necessary.id},
        )
        self.assertEqual(
            response.context["selected_kinds"], {"Entrata", "Uscita necessaria"}
        )
        self.assertEqual(
            response.context["selected_account_ids"], {self.a.id, self.b.id}
        )
        self.assertRegex(
            response.content.decode(), r'name="tipo"\s+value="Entrata"\s+checked'
        )
        self.assertRegex(
            response.content.decode(), rf'name="conto"\s+value="{self.a.id}"\s+checked'
        )

        no_selection = self.client.get(
            reverse("transactions"),
            {
                "categoria": "",
                "sottocategoria": "",
                "tipo": "",
                "conto": "",
            },
        )
        self.assertEqual(no_selection.context["page"].paginator.count, 0)

    def test_transfers_change_individual_accounts_but_not_consolidated_balance_or_totals(
        self,
    ):
        day = date(2026, 5, 5)
        Transfer.objects.create(
            date=day,
            order_index=1,
            source=self.a,
            destination=self.b,
            amount=Decimal("120.00"),
        )
        self.assertEqual(balance_at(day, {self.a.id}), Decimal("880.00"))
        self.assertEqual(balance_at(day, {self.b.id}), Decimal("120.00"))
        self.assertEqual(balance_at(day), Decimal("1000.00"))
        response = self.client.get(
            reverse("dashboard"), {"inizio": "2026-05-05", "fine": "2026-05-05"}
        )
        self.assertEqual(response.context["income"], Decimal("0.00"))
        self.assertEqual(response.context["outgoing"], Decimal("0.00"))
        self.assertEqual(response.context["net"], Decimal("0.00"))

    def test_transfer_can_be_edited_and_deleted_as_one_linked_operation(self):
        day = date(2026, 5, 5)
        transfer = Transfer.objects.create(
            date=day,
            order_index=1,
            source=self.a,
            destination=self.b,
            amount=Decimal("120.00"),
            description="Spostamento risparmi",
        )

        edit_page = self.client.get(reverse("transfer_edit", args=[transfer.uid]))
        self.assertEqual(edit_page.status_code, 200)
        self.assertContains(edit_page, "Modifica giroconto")
        self.assertEqual(edit_page.context["form"].instance.pk, transfer.pk)

        response = self.client.post(
            reverse("transfer_edit", args=[transfer.uid]),
            {
                "date": "2026-05-06",
                "operation_time": "09:30",
                "source": self.b.id,
                "destination": self.a.id,
                "amount": "80.00",
                "description": "Rientro risparmi",
            },
        )
        self.assertRedirects(response, reverse("transactions"))
        transfer.refresh_from_db()
        self.assertEqual(transfer.date, date(2026, 5, 6))
        self.assertEqual(transfer.operation_time.strftime("%H:%M"), "09:30")
        self.assertEqual(transfer.source, self.b)
        self.assertEqual(transfer.destination, self.a)
        self.assertEqual(transfer.amount, Decimal("80.00"))
        self.assertEqual(transfer.description, "Rientro risparmi")
        self.assertEqual(Transfer.objects.count(), 1)
        self.assertEqual(balance_at(date(2026, 5, 6), {self.a.id}), Decimal("1080.00"))
        self.assertEqual(balance_at(date(2026, 5, 6), {self.b.id}), Decimal("-80.00"))
        self.assertEqual(balance_at(date(2026, 5, 6)), Decimal("1000.00"))

        movements = self.client.get(
            reverse("transactions"), {"conto": str(self.a.id), "tipo": "Trasferimento"}
        )
        self.assertContains(movements, reverse("transfer_edit", args=[transfer.uid]))
        self.assertContains(movements, reverse("transfer_delete", args=[transfer.uid]))
        self.assertContains(movements, "Giroconto")

        delete_url = reverse("transfer_delete", args=[transfer.uid])
        self.assertEqual(self.client.get(delete_url).status_code, 405)
        response = self.client.post(delete_url)
        self.assertRedirects(response, reverse("transactions"))
        self.assertFalse(Transfer.objects.filter(pk=transfer.pk).exists())
        self.assertEqual(balance_at(date(2026, 5, 6), {self.a.id}), Decimal("1000.00"))
        self.assertEqual(balance_at(date(2026, 5, 6), {self.b.id}), Decimal("0.00"))
        self.assertEqual(balance_at(date(2026, 5, 6)), Decimal("1000.00"))

    def test_transfer_only_history_sets_the_default_dashboard_period(self):
        today = timezone.localdate()
        first_day = today - timedelta(days=1)
        Transfer.objects.create(
            date=first_day,
            order_index=1,
            source=self.a,
            destination=self.b,
            amount=Decimal("12.00"),
        )
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["earliest"], first_day.isoformat())
        self.assertEqual(response.context["start"], first_day.isoformat())

    def test_account_movements_show_linked_transfer_sides_with_running_balances_and_csv(
        self,
    ):
        day = date(2026, 5, 5)
        self.tx(
            day,
            self.salary,
            "100.00",
            9,
            account=self.a,
            description="Accredito precedente",
        )
        outgoing = Transfer.objects.create(
            date=day,
            order_index=10,
            source=self.a,
            destination=self.b,
            amount=Decimal("120.00"),
            description="Versamento risparmi",
        )
        incoming = Transfer.objects.create(
            date=day,
            order_index=11,
            source=self.b,
            destination=self.a,
            amount=Decimal("45.00"),
            description="Rientro risparmi",
        )
        self.tx(
            day,
            self.necessary,
            "5.00",
            12,
            account=self.a,
            description="Spesa successiva",
        )
        params = {
            "conto": str(self.a.id),
            "inizio": "05/05/2026",
            "fine": "05/05/2026",
            "tipo": "Trasferimento",
        }
        response = self.client.get(reverse("transactions"), params)
        self.assertEqual(response.status_code, 200)
        rows = list(response.context["page"].object_list)
        self.assertEqual(len(rows), 2)
        by_direction = {row.direction: row for row in rows}
        self.assertEqual(by_direction["Uscita"].uid, outgoing.uid)
        self.assertEqual(by_direction["Uscita"].balance_after, Decimal("980.00"))
        self.assertFalse(by_direction["Uscita"].is_positive)
        self.assertEqual(by_direction["Entrata"].uid, incoming.uid)
        self.assertEqual(by_direction["Entrata"].balance_after, Decimal("1025.00"))
        self.assertTrue(by_direction["Entrata"].is_positive)
        self.assertContains(response, "Trasferimento in uscita")
        self.assertContains(response, "Trasferimento in entrata")

        incoming_only = self.client.get(
            reverse("transactions"),
            {
                **params,
                "tipo": ["Trasferimento in entrata"],
            },
        )
        self.assertEqual(len(incoming_only.context["page"].object_list), 1)
        self.assertEqual(incoming_only.context["page"].object_list[0].uid, incoming.uid)

        export = self.client.get(reverse("export_csv"), params)
        self.assertEqual(export.status_code, 200)
        exported_rows = list(
            csv.reader(export.content.decode("utf-8-sig").splitlines(), delimiter=";")
        )[1:]
        self.assertEqual([row[2] for row in exported_rows], ["-120,00", "45,00"])
        self.assertEqual([row[3] for row in exported_rows], ["Giroconto", "Giroconto"])
        self.assertEqual(
            [row[5] for row in exported_rows],
            ["Trasferimento in uscita", "Trasferimento in entrata"],
        )
        self.assertEqual([row[6] for row in exported_rows], ["980,00", "1025,00"])

    def _prepare_import(self, csv_text):
        upload = SimpleUploadedFile(
            "estratto.csv", csv_text.encode("utf-8"), content_type="text/csv"
        )
        response = self.client.post(
            reverse("import"), {"stage": "upload", "file": upload}
        )
        self.assertEqual(response.status_code, 302)
        mapping = {
            "date": 0,
            "description": 1,
            "amount": 2,
            "account": 3,
            "category": 4,
            "subcategory": 5,
            "external_id": 6,
        }
        payload = {"stage": "analyze", "date_format": "%d/%m/%Y"}
        payload.update({f"map_{key}": str(value) for key, value in mapping.items()})
        response = self.client.post(reverse("import"), payload)
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse("import"))
        self.assertEqual(response.status_code, 200)
        return response

    def test_csv_import_round_trip_with_italian_values_and_duplicate_detection(self):
        content = "Data;Descrizione;Importo;Conto;Categoria;Sottocategoria;Identificativo\n24/09/2026;Spesa mercato;-12,50;Carta;Supermercati;Supermercato;csv-001\n"
        review = self._prepare_import(content)
        self.assertEqual(review.context["ok_count"], 1)
        response = self.client.post(reverse("import_confirm"), {"confirm": "yes"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Transaction.objects.count(), 1)
        tx = Transaction.objects.get()
        self.assertEqual(tx.amount, Decimal("12.50"))
        self.assertEqual(tx.kind, "Uscita necessaria")
        self.assertEqual(balance_at(date(2026, 9, 24), {self.a.id}), Decimal("987.50"))
        review = self._prepare_import(content)
        self.assertEqual(review.context["duplicate_count"], 1)
        self.client.post(reverse("import_confirm"), {"confirm": "yes"})
        self.assertEqual(Transaction.objects.count(), 1)

    def test_import_confirmation_accepts_review_form_above_django_default_field_limit(
        self,
    ):
        count = 180
        rows = [
            "Data;Descrizione;Importo;Conto;Categoria;Sottocategoria;Identificativo"
        ]
        rows.extend(
            f"24/09/2026;Acquisto {index};-1,00;Carta;Supermercati;Supermercato;bulk-{index}"
            for index in range(count)
        )
        review = self._prepare_import("\n".join(rows))
        self.assertEqual(review.context["ok_count"], count)

        post_data = {"confirm": "yes"}
        for row in review.context["rows"]:
            index = row["row"]
            post_data.update(
                {
                    f"date_{index}": row["date"],
                    f"time_{index}": row["operation_time"],
                    f"description_{index}": row["description"],
                    f"amount_{index}": row["amount"],
                    f"account_{index}": row["account_name"],
                    f"subcategory_{index}": str(row["subcategory_id"]),
                }
            )
        self.assertGreater(len(post_data), 1000)
        response = self.client.post(reverse("import_confirm"), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Transaction.objects.count(), count)

    def test_separate_income_expense_columns_and_operation_time_are_supported(self):
        content = "Data;Ora;Descrizione;Entrate;Uscite;Conto;Categoria;Sottocategoria\n10/06/2026;10:00;Spesa;;10,00;Carta;Supermercati;Supermercato\n10/06/2026;09:00;Stipendio;50,00;;Carta;Entrate;Stipendio\n"
        upload = SimpleUploadedFile(
            "estratto.csv", content.encode("utf-8"), content_type="text/csv"
        )
        self.client.post(reverse("import"), {"stage": "upload", "file": upload})
        mapping = {
            "date": 0,
            "time": 1,
            "description": 2,
            "income": 3,
            "expense": 4,
            "account": 5,
            "category": 6,
            "subcategory": 7,
        }
        payload = {"stage": "analyze", "date_format": "%d/%m/%Y"}
        payload.update({f"map_{key}": str(value) for key, value in mapping.items()})
        self.client.post(reverse("import"), payload)
        review = self.client.get(reverse("import"))
        self.assertEqual(review.context["ok_count"], 2)
        self.client.post(reverse("import_confirm"), {"confirm": "yes"})
        expense = Transaction.objects.get(description="Spesa")
        salary = Transaction.objects.get(description="Stipendio")
        self.assertEqual(expense.operation_time.strftime("%H:%M"), "10:00")
        self.assertEqual(salary.operation_time.strftime("%H:%M"), "09:00")
        after = balances_after_transactions(self.a.id)
        self.assertEqual(after[salary.id], Decimal("1050.00"))
        self.assertEqual(after[expense.id], Decimal("1040.00"))

    def test_import_preview_keeps_invalid_rows_visible_for_correction(self):
        content = "Data;Descrizione;Importo;Conto;Categoria;Sottocategoria\n31/31/2026;Riga rotta;abc;Carta;Nuova;Ignoto\n"
        review = self._prepare_import(content)
        self.assertEqual(review.context["repair_count"], 1)
        row = review.context["rows"][0]
        self.assertEqual(row["status"], "correggere")
        self.assertTrue(row["errors"])

    def test_cancel_import_does_not_require_confirmation_or_submit_review_rows(self):
        review = self._prepare_import(
            "Data;Descrizione;Importo;Conto;Categoria;Sottocategoria;Identificativo\n"
            "24/09/2026;Spesa in anteprima;-12,50;Carta;Supermercati;Supermercato;cancel-001\n"
        )
        self.assertContains(review, 'form="cancel-import"')
        self.assertContains(review, "formnovalidate")
        self.assertIn("wallet_import_rows", self.client.session)

        # The cancel form posts only stage=clear; it needs no confirmation checkbox.
        cancelled = self.client.post(reverse("import"), {"stage": "clear"})
        self.assertEqual(cancelled.status_code, 302)
        self.assertNotIn("wallet_import_rows", self.client.session)
        self.assertNotIn("wallet_import_raw", self.client.session)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_import_reconstructs_opening_balance_from_progressive_balance(self):
        content = "Data;Descrizione;Importo;Conto;Categoria;Sottocategoria;Saldo;Identificativo\n24/09/2026;Market;-10,00;Importato;Supermercati;Supermercato;490,00;bal-1\n"
        upload = SimpleUploadedFile(
            "saldo.csv", content.encode("utf-8"), content_type="text/csv"
        )
        self.client.post(reverse("import"), {"stage": "upload", "file": upload})
        mapping = {
            "date": 0,
            "description": 1,
            "amount": 2,
            "account": 3,
            "category": 4,
            "subcategory": 5,
            "balance": 6,
            "external_id": 7,
        }
        payload = {"stage": "analyze", "date_format": "%d/%m/%Y"}
        payload.update({f"map_{key}": str(value) for key, value in mapping.items()})
        self.client.post(reverse("import"), payload)
        review = self.client.get(reverse("import"))
        self.assertTrue(review.context["balance_checks"]["Importato"]["consistent"])
        self.client.post(reverse("import_confirm"), {"confirm": "yes"})
        imported_account = Account.objects.get(name="Importato")
        self.assertEqual(imported_account.initial_balance, Decimal("500.00"))
        self.assertEqual(
            balance_at(date(2026, 9, 24), {imported_account.id}), Decimal("490.00")
        )

    def test_import_without_progressive_balance_requires_and_saves_opening_balance(
        self,
    ):
        content = "Data;Descrizione;Importo;Conto;Categoria;Sottocategoria\n24/09/2026;Market;-10,00;Nuovo;Supermercati;Supermercato\n"
        review = self._prepare_import(content)
        self.assertIn("Nuovo", review.context["opening_accounts"])
        self.client.post(
            reverse("import_confirm"),
            {"confirm": "yes", "initial_0": "150,00", "account_index_Nuovo": "0"},
        )
        account = Account.objects.get(name="Nuovo")
        self.assertEqual(account.initial_balance, Decimal("150.00"))
        self.assertEqual(balance_at(date(2026, 9, 24), {account.id}), Decimal("140.00"))

    def test_wallet_backup_json_round_trip_preserves_data_and_login(self):
        self.tx(
            date(2026, 7, 8),
            self.necessary,
            "42.35",
            1,
            description="Spesa da conservare",
        )
        Transfer.objects.create(
            date=date(2026, 7, 9),
            source=self.a,
            destination=self.b,
            amount=Decimal("15.00"),
            order_index=2,
        )
        backup_response = self.client.post(reverse("backup"), {"action": "download"})
        self.assertEqual(backup_response.status_code, 200)
        self.assertIn("application/json", backup_response["Content-Type"])
        fixture = json.loads(backup_response.content)
        self.assertTrue(any(row["model"] == "wallet.transaction" for row in fixture))

        Transaction.objects.all().delete()
        Transfer.objects.all().delete()
        Subcategory.objects.all().delete()
        Category.objects.all().delete()
        Account.objects.all().delete()
        upload = SimpleUploadedFile(
            "wallet_backup.json",
            backup_response.content,
            content_type="application/json",
        )
        restored = self.client.post(
            reverse("restore_backup"),
            {"action": "restore", "confirm": "yes", "file": upload},
        )
        self.assertEqual(restored.status_code, 302)
        self.assertEqual(Transaction.objects.get().description, "Spesa da conservare")
        self.assertEqual(Transfer.objects.count(), 1)
        self.assertEqual(Account.objects.count(), 2)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_backup_restore_requires_explicit_confirmation(self):
        self.tx(date(2026, 7, 8), self.necessary, "42.35", 1)
        backup_response = self.client.post(reverse("backup"), {"action": "download"})
        upload = SimpleUploadedFile(
            "wallet_backup.json",
            backup_response.content,
            content_type="application/json",
        )
        self.client.post(
            reverse("restore_backup"), {"action": "restore", "file": upload}
        )
        self.assertEqual(Transaction.objects.count(), 1)


class AccessControlTests(TestCase):
    def test_wallet_pages_require_login_but_login_and_health_check_are_public(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)
        self.assertEqual(self.client.get(reverse("healthz")).status_code, 200)

    @override_settings(
        SECURE_SSL_REDIRECT=True, SECURE_REDIRECT_EXEMPT=[r"^healthz/?$"]
    )
    def test_plain_http_readiness_probe_is_not_redirected(self):
        self.assertEqual(self.client.get(reverse("healthz")).status_code, 200)

    def test_valid_login_opens_private_dashboard(self):
        get_user_model().objects.create_superuser(
            username="wallet-owner", password="password-test-sicura-1"
        )
        response = self.client.post(
            reverse("login"),
            {"username": "wallet-owner", "password": "password-test-sicura-1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("password_change")).status_code, 200)


class BundledTaxonomyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="wallet-owner", password="password-test-sicura-1"
        )
        self.client.force_login(self.user)

    def test_bundled_csv_contains_the_complete_taxonomy_and_accounting_kinds(self):
        taxonomy_file = Path(__file__).resolve().parents[1] / "categorie_movimenti.csv"
        with taxonomy_file.open("rb") as source:
            imported_count = import_taxonomy(source)
        self.assertEqual(imported_count, 95)
        self.assertEqual(Category.objects.filter(active=True).count(), 19)
        self.assertEqual(Subcategory.objects.filter(active=True).count(), 95)
        supermarket = Subcategory.objects.get(
            category__name="Supermercati", name="Supermercato"
        )
        bar = Subcategory.objects.get(
            category__name="Bar e ristoranti", name="Bar / Caffè"
        )
        insurance = Subcategory.objects.get(
            category__name="Tasse, assicurazioni e commissioni", name="Assicurazioni"
        )
        furniture = Subcategory.objects.get(
            category__name="Casa", name="Arredi / Articoli per la casa"
        )
        animal_food = Subcategory.objects.get(category__name="Animali", name="Cibo")
        animal_accessories = Subcategory.objects.get(
            category__name="Animali", name="Accessori"
        )
        self.assertEqual(supermarket.kind, "Uscita necessaria")
        self.assertEqual(supermarket.category.color, "#EA580C")
        self.assertEqual(bar.kind, "Uscita extra")
        self.assertEqual(bar.category.color, "#F97316")
        self.assertEqual(insurance.kind, "Uscita necessaria")
        self.assertEqual(furniture.kind, "Uscita extra")
        self.assertEqual(animal_food.kind, "Uscita necessaria")
        self.assertEqual(animal_accessories.kind, "Uscita extra")

    def test_categories_page_imports_bilingual_csv_and_preserves_archived_history(self):
        old_category = Category.objects.create(
            name="Categoria obsoleta", color="#64748B"
        )
        old_subcategory = Subcategory.objects.create(
            category=old_category,
            name="Bar",
            kind="Uscita extra",
        )
        account = Account.objects.create(name="Carta")
        transaction = Transaction.objects.create(
            date=date(2026, 9, 24),
            amount=Decimal("12.50"),
            kind="Uscita extra",
            subcategory=old_subcategory,
            account=account,
        )
        bilingual_csv = (
            "Category_EN,Subcategory_EN,Category_IT,Subcategory_IT,Color,Type_EN,Type_IT\n"
            "Income,Salary,Entrate,Stipendio,#16A34A,Income,Entrata\n"
            'Taxes,Insurance,"Tasse, assicurazioni e commissioni",Assicurazioni,#92400E,Necessary expense,Uscita necessaria\n'
        ).encode("utf-8")
        upload = SimpleUploadedFile(
            "categorie_bilingue.csv", bilingual_csv, content_type="text/csv"
        )

        response = self.client.post(reverse("categories"), {"file": upload})

        self.assertRedirects(response, reverse("categories"))
        old_category.refresh_from_db()
        self.assertFalse(old_category.active)
        old_subcategory.refresh_from_db()
        self.assertFalse(old_subcategory.active)
        transaction.refresh_from_db()
        self.assertEqual(transaction.kind, "Uscita extra")
        self.assertEqual(transaction.amount, Decimal("12.50"))
        self.assertTrue(
            Subcategory.objects.get(category__name="Entrate", name="Stipendio").active
        )
        imported_insurance = Subcategory.objects.get(
            category__name="Tasse, assicurazioni e commissioni",
            name="Assicurazioni",
        )
        self.assertEqual(imported_insurance.kind, "Uscita necessaria")
