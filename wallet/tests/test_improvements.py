"""Interchange, atomicity and SQL accounting regressions."""

import csv
import io
from copy import deepcopy
from datetime import date, time
from decimal import Decimal as D
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.paginator import Paginator
from django.db import connection
from django.http import QueryDict
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from wallet.models import Account, Category, Subcategory, Transaction, Transfer
from wallet.services import balance_at, ledger_snapshot
from wallet.services.analytics import analytics
from wallet.services.csv_wallet import import_wallet_csv
from wallet.services.filters import Filters
from wallet.services.movements import movement_rows, list_groups
from wallet.services.tabular import read_tabular


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ImprovementsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="wallet-owner", password="test-only"
        )
        cls.a = Account.objects.create(name="Conto A", initial_balance=D("1000.10"))
        cls.b = Account.objects.create(name="Carta B", initial_balance=D("-10.02"))
        cls.cat = Category.objects.create(name="Spese test")
        cls.sub = Subcategory.objects.create(
            category=cls.cat, name="Acquisti", kind="Uscita extra"
        )
        cls.inc = Subcategory.objects.create(
            category=cls.cat, name="Rimborsi", kind="Entrata"
        )

    def setUp(self):
        self.client.force_login(self.user)

    def tx(self, **kw):
        return Transaction.objects.create(
            **dict(
                dict(
                    date=date(2026, 5, 5),
                    account=self.a,
                    subcategory=self.sub,
                    amount=D("0.10"),
                    order_index=3,
                    description="Acquisto",
                ),
                **kw,
            )
        )

    def transfer(self, **kw):
        return Transfer.objects.create(
            **dict(
                dict(
                    date=date(2026, 5, 5),
                    source=self.a,
                    destination=self.b,
                    amount=D("15.23"),
                    order_index=2,
                ),
                **kw,
            )
        )

    def filters(self, query=""):
        return Filters.parse(
            QueryDict("periodo=custom&inizio=01/05/2026&fine=31/05/2026&" + query)
        )

    def exported(self, query=""):
        r = self.client.get(
            reverse("export_csv")
            + "?periodo=custom&inizio=01/05/2026&fine=31/05/2026&"
            + query
        )
        self.assertEqual(r.status_code, 200)
        rows = list(
            csv.reader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";")
        )
        return {"headers": rows[0], "rows": rows[1:], "delimiter": ";"}

    def edit(self, raw, row, **changes):
        for name, value in changes.items():
            raw["rows"][row][raw["headers"].index(name)] = str(value)

    def test_native_roundtrip_empty_archive_preserves_uids_links_order_and_balances(
        self,
    ):
        tx = self.tx(
            operation_time=time(10, 4, 3, 123456),
            notes="'nota\nseconda riga",
            external_id="banca-1",
        )
        self.tx(
            subcategory=self.inc,
            amount=D("1500.45"),
            order_index=1,
            operation_time=time(8),
        )
        tr = self.transfer(operation_time=time(9, 10, 5, 123456))
        raw = self.exported()
        before = {
            a.name: balance_at(date(2026, 5, 31), {a.pk}) for a in (self.a, self.b)
        }
        before_rows = [
            (str(r.uid), r.account.name, r.balance_after)
            for r in movement_rows(self.filters(), "date")[0]
        ]
        Transaction.objects.all().delete()
        Transfer.objects.all().delete()
        Subcategory.objects.all().delete()
        Category.objects.all().delete()
        Account.objects.all().delete()
        preview = import_wallet_csv(raw)
        self.assertEqual((preview["movements"], preview["transfers"]), (2, 1))
        self.assertFalse(Account.objects.exists())
        result = import_wallet_csv(raw, commit=True)
        self.assertEqual(result["added"], 3)
        restored = Transaction.objects.get(uid=tx.uid)
        self.assertEqual(
            (restored.notes, restored.operation_time, restored.order_index),
            (tx.notes, tx.operation_time, tx.order_index),
        )
        restored_transfer = Transfer.objects.get(uid=tr.uid)
        self.assertEqual(restored_transfer.source.name, self.a.name)
        self.assertEqual(restored_transfer.destination.name, self.b.name)
        after = {
            a.name: balance_at(date(2026, 5, 31), {a.pk}) for a in Account.objects.all()
        }
        self.assertEqual(before, after)
        self.assertEqual(
            before_rows,
            [
                (str(r.uid), r.account.name, r.balance_after)
                for r in movement_rows(self.filters(), "date")[0]
            ],
        )
        again = import_wallet_csv(raw, commit=True)
        self.assertEqual((again["added"], again["duplicates"]), (0, 3))

    def test_filtered_single_transfer_leg_restores_both_accounts(self):
        tr = self.transfer()
        raw = self.exported(f"conto={self.a.pk}")
        self.assertEqual(len(raw["rows"]), 1)
        Transfer.objects.all().delete()
        result = import_wallet_csv(raw, commit=True)
        self.assertEqual((result["transfers"], result["single_legs"]), (1, 1))
        self.assertTrue(Transfer.objects.filter(uid=tr.uid).exists())
        self.assertEqual(balance_at(date(2026, 5, 31), {self.b.pk}), D("5.21"))

    def test_conflicting_pair_and_same_account_transfer_are_rejected(self):
        self.transfer()
        raw = self.exported()
        Transfer.objects.all().delete()
        for changes in (
            {"Descrizione": "discordante"},
            {"Conto destinazione": self.a.name},
            {"Tipo": "Entrata"},
            {"Importo": "0"},
        ):
            malformed = deepcopy(raw)
            self.edit(malformed, 0, **changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                import_wallet_csv(malformed, commit=True)
            self.assertFalse(Transfer.objects.exists())

    def test_existing_uuid_conflict_rolls_back_new_accounts_and_categories(self):
        self.tx()
        raw = self.exported()
        self.edit(
            raw,
            0,
            **{
                "Conto o carta": "Nuovo conto",
                "Categoria": "Nuova categoria",
                "Sottocategoria": "Nuova voce",
            },
        )
        with self.assertRaisesRegex(ValueError, "UUID"):
            import_wallet_csv(raw, commit=True)
        self.assertFalse(Account.objects.filter(name="Nuovo conto").exists())
        self.assertFalse(Category.objects.filter(name="Nuova categoria").exists())
        self.assertEqual(Transaction.objects.count(), 1)

    def test_second_import_does_not_duplicate_even_when_rows_repeated(self):
        self.tx()
        self.transfer()
        raw = self.exported()
        raw["rows"] += deepcopy(raw["rows"])
        result = import_wallet_csv(raw, commit=True)
        self.assertEqual((result["added"], result["duplicates"]), (0, 2))
        self.assertEqual(
            (Transaction.objects.count(), Transfer.objects.count()), (1, 1)
        )

    def test_same_external_id_with_different_uuid_is_conflict(self):
        from uuid import uuid4

        self.tx(external_id="bank-1")
        raw = self.exported()
        self.edit(raw, 0, **{"UUID operazione": str(uuid4())})
        with self.assertRaisesRegex(ValueError, "Identificativo esterno"):
            import_wallet_csv(raw, commit=True)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_wallet_csv_formula_escaping_is_reversible(self):
        for i, text in enumerate(
            [
                "=1+1",
                "+test",
                "-nota",
                "@foo",
                "'=gia escaped",
                "'normale",
                "  =formula",
                "\tformula",
            ]
        ):
            self.tx(description=text, order_index=i, notes=text)
        raw = self.exported()
        descriptions = set(Transaction.objects.values_list("description", flat=True))
        Transaction.objects.all().delete()
        import_wallet_csv(raw, commit=True)
        self.assertEqual(
            descriptions, set(Transaction.objects.values_list("description", flat=True))
        )
        for tx in Transaction.objects.all():
            self.assertEqual(tx.description, tx.notes)

    def test_archived_taxonomy_roundtrip_and_existing_opening_is_preserved(self):
        self.tx()
        raw = self.exported()
        self.sub.active = False
        self.sub.save()
        self.cat.active = False
        self.cat.save()
        self.a.initial_balance = 500
        self.a.save()
        result = import_wallet_csv(raw, commit=True)
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(result["balance_warnings"], 1)
        self.a.refresh_from_db()
        self.assertEqual(self.a.initial_balance, D("500"))

    def test_malformed_schema_and_unsupported_version_are_rejected(self):
        self.tx()
        raw = self.exported()
        for column, bad in [
            ("Formato Wallet", "999"),
            ("UUID operazione", "invalid"),
            ("Ordine", "-1"),
            ("Orario", "24:01"),
            ("Importo", "1.234,567"),
        ]:
            malformed = deepcopy(raw)
            self.edit(malformed, 0, **{column: bad})
            with self.subTest(column=column), self.assertRaises(ValueError):
                import_wallet_csv(malformed)
        raw["headers"].pop()
        with self.assertRaises(ValueError):
            import_wallet_csv(raw)

    def test_upload_detects_wallet_csv_and_requires_confirmation(self):
        self.transfer()
        raw = self.exported()
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(raw["headers"])
        writer.writerows(raw["rows"])
        Transfer.objects.all().delete()
        upload = SimpleUploadedFile(
            "wallet.csv", buffer.getvalue().encode("utf-8"), content_type="text/csv"
        )
        self.client.post(reverse("import"), {"stage": "upload", "file": upload})
        review = self.client.get(reverse("import"))
        self.assertContains(review, "Conferma importazione")
        self.assertEqual(review.context["transfers"], 1)
        self.assertFalse(Transfer.objects.exists())
        self.client.post(reverse("import_confirm"), {})
        self.assertFalse(Transfer.objects.exists())
        response = self.client.post(reverse("import_confirm"), {"confirm": "yes"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Transfer.objects.count(), 1)
        self.assertNotIn("wallet_import_native", self.client.session)

    def test_limit_applies_to_csv_and_excel_while_reading(self):
        from openpyxl import Workbook

        text = "Data;Importo\n" + "01/01/2026;1\n" * 10001
        with self.assertRaisesRegex(ValueError, "10.000"):
            read_tabular(SimpleUploadedFile("many.csv", text.encode()))
        book = Workbook()
        book.active.append(["Data", "Importo"])
        for i in range(4):
            book.active.append(["01/01/2026", i])
        stream = io.BytesIO()
        book.save(stream)
        with self.assertRaises(ValueError):
            read_tabular(SimpleUploadedFile("many.xlsx", stream.getvalue()), max_rows=3)

    def test_sql_register_balances_match_independent_ledger_under_filters(self):
        for i in range(35):
            self.tx(
                date=date(2026, 4 + i % 2, i % 28 + 1),
                account=self.a if i % 3 else self.b,
                operation_time=time(9, i) if i % 2 else None,
                order_index=i % 4,
                amount=D(i + 1) / 100,
                description="Visibile" if i % 3 else "Nascosto",
            )
        for i in range(8):
            self.transfer(
                date=date(2026, 5, i + 1), order_index=i, operation_time=time(8)
            )
        expected = ledger_snapshot(None, start=date.min, end=date.max, as_of=date.max)
        for query in (
            "",
            f"conto={self.a.pk}",
            "q=Visibile",
            "giroconti=0",
            "tipo=Uscita+extra",
            "categoria=",
        ):
            rows, _ = movement_rows(self.filters(query), "date")
            for row in rows:
                if row.is_transfer:
                    leg = "transfer_in" if row.is_positive else "transfer_out"
                    pk = int(row.id.split("-")[0])
                    self.assertEqual(
                        row.balance_after, expected.transfer_balances[(pk, leg)]
                    )
                else:
                    self.assertEqual(
                        row.balance_after, expected.transaction_balances[row.pk][0]
                    )

    def test_database_sorts_all_columns_and_paginates_before_hydration(self):
        Transaction.objects.bulk_create(
            [
                Transaction(
                    date=date(2026, 5, 5),
                    account=self.a,
                    subcategory=self.sub,
                    kind=self.sub.kind,
                    description=f"Test {i:04}",
                    amount=D(i + 1) / 100,
                    order_index=i,
                )
                for i in range(230)
            ]
        )
        self.transfer()
        filters = self.filters()
        with CaptureQueriesContext(connection) as captured:
            rows, _ = movement_rows(filters, "-amount")
            page = Paginator(rows, 25).get_page(2)
            visible = list(page.object_list)
            groups = list_groups(rows, visible)
        self.assertEqual(len(visible), 25)
        self.assertEqual(page.paginator.count, 232)
        self.assertTrue(any("LIMIT 25 OFFSET 25" in q["sql"] for q in captured))
        self.assertLess(len(captured), 7)
        self.assertEqual(
            groups[0]["net"], -sum((D(i + 1) / 100 for i in range(230)), D(0))
        )
        for field, key in [
            ("date", lambda r: r.date),
            ("description", lambda r: r.description.lower()),
            ("amount", lambda r: r.signed_amount),
            ("kind", lambda r: r.display_type),
            ("account", lambda r: r.account.name),
            ("category", lambda r: r.display_category),
            ("subcategory", lambda r: r.display_subcategory),
            ("balance", lambda r: r.balance_after),
        ]:
            with self.subTest(sort=field):
                result = list(movement_rows(filters, field)[0])
                self.assertEqual(
                    [key(r) for r in result], sorted(key(r) for r in result)
                )
                self.assertEqual(
                    [r.id for r in result],
                    list(
                        reversed([r.id for r in movement_rows(filters, "-" + field)[0]])
                    ),
                )

    def test_integer_cent_aggregates_are_exact_for_large_amounts_and_fractional_cents(
        self,
    ):
        self.tx(amount=D("999999999999.99"), subcategory=self.inc)
        Transaction.objects.bulk_create(
            [
                Transaction(
                    date=date(2026, 5, 5),
                    account=self.a,
                    subcategory=self.sub,
                    kind=self.sub.kind,
                    amount=D("0.10"),
                )
                for _ in range(1001)
            ]
        )
        self.transfer()
        values = analytics(self.filters(), with_balance=True)
        self.assertEqual(values["income"], D("999999999999.99"))
        self.assertEqual(values["outgoing"], D("100.10"))
        self.assertEqual(values["closing"], D("1000000000889.97"))
        self.assertEqual(values["transaction_count"], 1002)
        self.assertEqual(values["donut_rows"][0]["count"], 1001)

    def test_generic_bulk_import_validates_all_rows_and_rolls_back(self):
        session = self.client.session
        rows = [
            dict(
                row=i,
                date="2026-05-05",
                amount="10.00",
                description="Valid" if i == 0 else "x" * 251,
                account_name=self.a.name,
                subcategory_id=self.sub.pk,
                operation_time="",
                external_id=f"id-{i}",
                balance="",
                status="ok",
            )
            for i in range(2)
        ]
        session["wallet_import_rows"] = rows
        session.save()
        self.client.post(reverse("import_confirm"), {"confirm": "yes"})
        self.assertFalse(Transaction.objects.exists())
        self.assertIn("wallet_import_rows", self.client.session)
        rows[-1]["description"] = "Valid too"
        session = self.client.session
        session["wallet_import_rows"] = rows
        session.save()
        with patch.object(
            Transaction,
            "save",
            side_effect=AssertionError("Per-row save is forbidden for imports"),
        ):
            response = self.client.post(reverse("import_confirm"), {"confirm": "yes"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Transaction.objects.count(), 2)

    def test_generic_duplicate_lookup_is_batched_and_deduplicates_same_file(self):
        rows = [
            dict(
                row=i,
                date="2026-05-05",
                amount="10.00",
                description=f"Batch {i}",
                account_name=self.a.name,
                subcategory_id=self.sub.pk,
                operation_time="",
                external_id=f"id-{i}",
                balance="",
                status="ok",
            )
            for i in range(200)
        ]
        rows.append(dict(rows[0], row=200))
        session = self.client.session
        session["wallet_import_rows"] = rows
        session.save()
        with CaptureQueriesContext(connection) as captured:
            response = self.client.post(reverse("import_confirm"), {"confirm": "yes"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["duplicates"], 1)
        self.assertEqual(Transaction.objects.count(), 200)
        self.assertLess(len(captured), 35)

    def test_midnight_and_missing_time_share_the_same_ordering_bucket(self):
        later = self.tx(order_index=5, operation_time=None)
        earlier = self.tx(order_index=1, operation_time=time.min)
        self.transfer(order_index=2, operation_time=time.min)
        expected = ledger_snapshot(None, start=date.min, end=date.max, as_of=date.max)
        rows = list(movement_rows(self.filters(), "date")[0])
        txs = [r for r in rows if not r.is_transfer]
        self.assertEqual([r.pk for r in txs], [earlier.pk, later.pk])
        for row in txs:
            self.assertEqual(
                row.balance_after, expected.transaction_balances[row.pk][0]
            )

    def test_native_database_failure_rolls_back_both_operation_types(self):
        from django.db import IntegrityError

        self.tx()
        self.transfer()
        raw = self.exported()
        Transaction.objects.all().delete()
        Transfer.objects.all().delete()
        with patch.object(
            Transfer.objects,
            "bulk_create",
            side_effect=IntegrityError("Simulated storage failure"),
        ):
            with self.assertRaises(IntegrityError):
                import_wallet_csv(raw, commit=True)
        self.assertFalse(Transaction.objects.exists())
        self.assertFalse(Transfer.objects.exists())
