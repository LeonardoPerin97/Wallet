import csv
import io
import json
import tempfile
from collections import defaultdict
from datetime import time as time_type
from decimal import Decimal
from pathlib import Path

from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.management import call_command
from django.db import transaction as db_transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..forms import RestoreForm, UploadForm
from ..models import (
    Account,
    Category,
    CategoryBudget,
    SubcategoryBudget,
    Subcategory,
    Transaction,
    Transfer,
    UserPreference,
)
from ..services import (
    ZERO,
    balance_before,
    guess_column,
    next_order_index,
    parse_date,
    parse_money,
    read_tabular,
)
from .movements import _movement_rows

from ..services.importing import FIELD_LABELS, _analyze_import, import_review_context
from ..services.csv_wallet import HEADERS, export_row, import_wallet_csv, is_wallet_csv


def _clear_import(session):
    for key in (
        "wallet_import_raw",
        "wallet_import_mapping",
        "wallet_import_rows",
        "wallet_import_date_format",
        "wallet_import_native",
    ):
        session.pop(key, None)


@login_required
def import_view(request):
    stage = request.POST.get("stage") if request.method == "POST" else ""
    form = UploadForm(request.POST or None, request.FILES or None)
    if stage == "upload" and form.is_valid():
        try:
            delimiter_choices = {
                "comma": ",",
                "semicolon": ";",
                "tab": "\t",
                "pipe": "|",
            }
            override = delimiter_choices.get(request.POST.get("delimiter", ""), "")
            headers, rows, delimiter = read_tabular(form.cleaned_data["file"], override)
            if len(rows) > 10000:
                raise ValueError(
                    "Il file contiene oltre 10.000 righe; dividilo in file più piccoli."
                )
            request.session["wallet_import_raw"] = {
                "headers": headers,
                "rows": [
                    [str(v if v is not None else "") for v in row] for row in rows
                ],
                "delimiter": delimiter,
            }
            request.session.pop("wallet_import_rows", None)
            request.session["wallet_import_native"] = is_wallet_csv(headers)
            return redirect("import")
        except Exception as exc:
            messages.error(request, f"File non leggibile: {exc}")
    raw = request.session.get("wallet_import_raw")
    if stage == "clear":
        _clear_import(request.session)
        return redirect("import")
    if raw and request.session.get("wallet_import_native"):
        try:
            context = import_wallet_csv(raw)
        except Exception as exc:
            context = {"import_error": str(exc)}
        return render(request, "wallet/import_wallet.html", context)
    if raw and stage == "analyze":
        mapping = {
            field: request.POST.get(f"map_{field}", "") for field, _, _ in FIELD_LABELS
        }
        missing = [
            label for field, label, _ in FIELD_LABELS[:1] if not mapping.get(field)
        ]
        if not any(mapping.get(k) for k in ("amount", "income", "expense")):
            missing.append("importo o colonne entrate/uscite")
        if (
            not mapping.get("account")
            and not request.POST.get("default_account", "").strip()
        ):
            missing.append("conto/carta predefinito (se nel file non c’è la colonna)")
        if missing:
            messages.error(request, "Associa data e importo e indica il conto.")
        else:
            default_account = request.POST.get("default_account", "").strip()
            analyzed = _analyze_import(
                raw, mapping, request.POST.get("date_format", "")
            )
            for row in sorted(
                analyzed,
                key=lambda x: (
                    x.get("date") or "9999-12-31",
                    x.get("operation_time") or "00:00:00",
                    x["row"],
                ),
            ):
                if not row["account_name"]:
                    row["account_name"] = default_account
                if not row["account_name"]:
                    row["errors"].append("Conto o carta mancante")
                    row["status"] = "correggere"
            request.session["wallet_import_mapping"] = mapping
            request.session["wallet_import_rows"] = analyzed
            return redirect("import")
    analyzed = request.session.get("wallet_import_rows")
    if raw and not analyzed:
        headers = raw["headers"]
        guesses = {
            field: guess_column(headers, patterns)
            for field, _, patterns in FIELD_LABELS
        }
        fields_data = [
            {"key": field, "label": label, "guess": guesses[field]}
            for field, label, _ in FIELD_LABELS
        ]
        return render(
            request,
            "wallet/import_map.html",
            {
                "form": form,
                "headers": headers,
                "rows": raw["rows"][:8],
                "delimiter": raw["delimiter"],
                "fields_data": fields_data,
                "accounts": Account.objects.filter(active=True),
            },
        )
    if analyzed:
        context = import_review_context(
            analyzed, request.session.get("wallet_import_mapping", {})
        )
        context["form"] = form
        return render(request, "wallet/import_review.html", context)
    return render(
        request,
        "wallet/import_upload.html",
        {"form": form, "accounts": Account.objects.filter(active=True)},
    )


@require_POST
@login_required
def import_confirm(request):
    if request.session.get("wallet_import_native"):
        if request.POST.get("confirm") != "yes":
            messages.error(
                request, "Conferma non ricevuta: nessun dato è stato salvato."
            )
            return redirect("import")
        try:
            context = import_wallet_csv(
                request.session.get("wallet_import_raw", {}), commit=True
            )
        except Exception as exc:
            messages.error(
                request, f"Importazione annullata senza salvare righe: {exc}"
            )
            return redirect("import")
        _clear_import(request.session)
        return render(request, "wallet/import_done.html", context)
    rows = request.session.get("wallet_import_rows")
    if not rows:
        messages.error(
            request, "La sessione d’importazione è scaduta. Carica di nuovo il file."
        )
        return redirect("import")
    if request.POST.get("confirm") != "yes":
        messages.error(request, "Conferma non ricevuta: nessun dato è stato salvato.")
        return redirect("import")
    inferred, cumulative = defaultdict(list), defaultdict(lambda: ZERO)
    prepared = []
    subs = {
        str(sub.id): sub
        for sub in Subcategory.objects.select_related("category").filter(
            active=True, category__active=True
        )
    }
    for row in rows:
        sub_id = request.POST.get(
            f"subcategory_{row['row']}", row.get("subcategory_id") or ""
        )
        sub = subs.get(str(sub_id))
        try:
            day = parse_date(
                request.POST.get(f"date_{row['row']}", row.get("date", ""))
            )
            amount = abs(
                parse_money(
                    request.POST.get(f"amount_{row['row']}", row.get("amount", ""))
                )
            )
            desc = request.POST.get(
                f"description_{row['row']}", row.get("description", "")
            ).strip()
            account_name = request.POST.get(
                f"account_{row['row']}", row.get("account_name", "")
            ).strip()
        except Exception:
            continue
        if not sub or not account_name or amount <= 0:
            continue
        import datetime as dt

        raw_time = request.POST.get(f"time_{row['row']}", row.get("operation_time", ""))
        try:
            operation_time = (
                dt.datetime.strptime(raw_time, "%H:%M:%S").time()
                if len(raw_time) == 8
                else (
                    dt.datetime.strptime(raw_time, "%H:%M").time() if raw_time else None
                )
            )
        except ValueError:
            continue
        prepared.append((row, sub, day, desc, amount, account_name, operation_time))
    if len(prepared) != len(rows):
        for row in rows:
            for field, target in [
                ("date", "date"),
                ("description", "description"),
                ("amount", "amount"),
                ("account", "account_name"),
                ("time", "operation_time"),
                ("subcategory", "subcategory_id"),
            ]:
                row[target] = request.POST.get(
                    f"{field}_{row['row']}", row.get(target, "")
                )
            row["errors"] = ["Controlla data, importo, conto e sottocategoria."]
            row["status"] = "correggere"
        request.session["wallet_import_rows"] = rows
        messages.error(
            request,
            "Nessuna riga salvata. Correggi tutte le righe evidenziate prima di confermare; la revisione è ancora disponibile.",
        )
        return redirect("import")
    prepared.sort(key=lambda x: (x[2], x[6] or time_type.min, x[0]["row"]))
    for row, sub, day, desc, amount, account_name, operation_time in prepared:
        signed = amount if sub.kind == "Entrata" else -amount
        cumulative[account_name] += signed
        if row.get("balance"):
            inferred[account_name].append(
                Decimal(row["balance"]) - cumulative[account_name]
            )
    added, duplicates, balance_warnings = 0, 0, 0
    skipped_for_correction = len(rows) - len(prepared)
    start_index = next_order_index()
    try:
        with db_transaction.atomic():
            for account_name, values in inferred.items():
                if not values:
                    continue
                account = Account.objects.filter(name__iexact=account_name).first()
                if not account:
                    continue
                has_ledger = (
                    account.transactions.exists()
                    or account.transfers_in.exists()
                    or account.transfers_out.exists()
                )
                if not has_ledger and account.initial_balance == ZERO:
                    account.initial_balance = values[0]
                    account.save(update_fields=["initial_balance"])
                else:
                    first_day = min(
                        x[2]
                        for x in prepared
                        if x[5].casefold() == account_name.casefold()
                    )
                    existing_balance = (
                        balance_before(first_day, {account.id})
                        if has_ledger
                        else account.initial_balance
                    )
                    if abs(existing_balance - values[0]) > Decimal("0.01"):
                        balance_warnings += 1
                if any(abs(v - values[0]) > Decimal("0.01") for v in values[1:]):
                    balance_warnings += 1
            for name in dict.fromkeys(x[5] for x in prepared):
                account = Account.objects.filter(name__iexact=name).first()
                if account and (
                    account.transactions.exists()
                    or account.transfers_in.exists()
                    or account.transfers_out.exists()
                ):
                    continue
                if inferred.get(name):
                    continue
                if account and account.initial_balance != ZERO:
                    continue
                idx = request.POST.get(f"account_index_{name}", "")
                try:
                    opening = parse_money(request.POST.get(f"initial_{idx}", "0"))
                except Exception as exc:
                    raise ValueError(
                        "Saldo iniziale non valido: controlla l’importo del conto."
                    ) from exc
                if account:
                    account.initial_balance = opening
                    account.save(update_fields=["initial_balance"])
                else:
                    account = Account(name=name, initial_balance=opening)
                    account.full_clean()
                    account.save()
            from ..services.import_duplicates import duplicate_index, signature
            from ..services.csv_wallet import validate_instance

            accounts = {a.name.casefold(): a for a in Account.objects.all()}
            # Resolve/create each account once, before validating the movement batch.
            for name in dict.fromkeys(x[5] for x in prepared):
                if name.casefold() in accounts:
                    continue
                values = inferred.get(name, [])
                idx = request.POST.get(f"account_index_{name}", "")
                opening = (
                    values[0]
                    if values
                    else parse_money(
                        request.POST.get(
                            f"initial_{idx}", request.POST.get("initial_default", "0")
                        )
                    )
                )
                account = Account(name=name, initial_balance=opening)
                account.full_clean()
                account.save()
                accounts[name.casefold()] = account
            specs = [
                (
                    accounts[name.casefold()].pk,
                    day,
                    desc,
                    amount,
                    row.get("external_id", ""),
                )
                for row, sub, day, desc, amount, name, clock in prepared
            ]
            external_ids, signatures = duplicate_index(specs)
            batch = []
            for row, sub, day, desc, amount, account_name, operation_time in prepared:
                account = accounts[account_name.casefold()]
                external_id = row.get("external_id", "")
                key = signature(account.pk, day, desc, amount)
                if (external_id and (account.pk, external_id) in external_ids) or (
                    key in signatures
                    and request.POST.get(f"include_duplicate_{row['row']}") != "on"
                ):
                    duplicates += 1
                    continue
                obj = Transaction(
                    date=day,
                    operation_time=operation_time,
                    order_index=start_index,
                    description=desc,
                    amount=amount,
                    subcategory=sub,
                    kind=sub.kind,
                    account=account,
                    external_id=external_id,
                    notes=row.get("notes", ""),
                )
                validate_instance(obj, ("account", "subcategory"))
                batch.append(obj)
                if external_id:
                    external_ids.add((account.pk, external_id))
                signatures.add(key)
                start_index += 1
            Transaction.objects.bulk_create(batch, batch_size=400)
            added = len(batch)

    except Exception as exc:
        messages.error(request, f"Importazione annullata senza salvare righe: {exc}")
        return redirect("import")
    for key in [
        "wallet_import_raw",
        "wallet_import_mapping",
        "wallet_import_rows",
        "wallet_import_date_format",
    ]:
        request.session.pop(key, None)
    messages.success(
        request,
        f"Importazione completata: {added} aggiunti, {duplicates} duplicati ignorati, {skipped_for_correction} da correggere.",
    )
    return render(
        request,
        "wallet/import_done.html",
        {
            "added": added,
            "duplicates": duplicates,
            "to_fix": skipped_for_correction,
            "balance_warnings": balance_warnings,
        },
    )


@login_required
def export_csv(request):
    items, _, _ = _movement_rows(request, sort_override="date")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="movimenti_wallet.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(HEADERS)
    for item in items:
        writer.writerow(export_row(item))
    return response


@login_required
def backup(request):
    if request.method == "POST" and request.POST.get("action") == "download":
        try:
            output = io.StringIO()
            call_command(
                "dumpdata",
                "wallet",
                format="json",
                indent=2,
                verbosity=0,
                stdout=output,
            )
        except Exception as exc:
            messages.error(request, f"Backup non creato: {exc}")
            return redirect("backup")
        response = HttpResponse(
            output.getvalue(), content_type="application/json; charset=utf-8"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="wallet_backup_{timezone.localdate():%Y%m%d}.json"'
        )
        return response
    return render(request, "wallet/backup.html", {"restore_form": RestoreForm()})


@login_required
def restore_backup(request):
    if request.method != "POST" or request.POST.get("action") != "restore":
        return redirect("backup")
    if request.POST.get("confirm") != "yes":
        messages.error(
            request,
            "Seleziona la conferma prima di ripristinare. Il database non è stato modificato.",
        )
        return redirect("backup")
    form = RestoreForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Seleziona un backup Wallet valido in formato JSON.")
        return redirect("backup")

    uploaded = form.cleaned_data["file"]
    try:
        raw = uploaded.read().decode("utf-8-sig")
        fixture = json.loads(raw)
        allowed_labels = {
            model._meta.label_lower
            for model in apps.get_app_config("wallet").get_models()
        }
        if not isinstance(fixture, list) or any(
            not isinstance(row, dict)
            or row.get("model") not in allowed_labels
            or not isinstance(row.get("fields"), dict)
            for row in fixture
        ):
            raise ValueError("Il contenuto non è un backup Wallet.")

        # Close the temporary file before Django opens it. This also works on
        # Windows, where an open NamedTemporaryFile cannot be reopened by name.
        # Authentication accounts remain intact; only wallet-owned data changes.
        with tempfile.TemporaryDirectory(prefix="wallet-backup-") as temp_dir:
            fixture_path = Path(temp_dir) / "wallet-backup.json"
            fixture_path.write_text(raw, encoding="utf-8")
            with db_transaction.atomic():
                Transaction.objects.all().delete()
                Transfer.objects.all().delete()
                UserPreference.objects.all().delete()
                SubcategoryBudget.objects.all().delete()
                CategoryBudget.objects.all().delete()
                Subcategory.objects.all().delete()
                Category.objects.all().delete()
                Account.objects.all().delete()
                call_command("loaddata", str(fixture_path), verbosity=0)
                for model in (
                    Account,
                    Category,
                    Subcategory,
                    Transaction,
                    Transfer,
                    CategoryBudget,
                    SubcategoryBudget,
                ):
                    for obj in model.objects.all().iterator():
                        obj.full_clean()
        messages.success(
            request,
            "Backup ripristinato. Conti, categorie e movimenti sono stati sostituiti dai dati del file.",
        )
    except Exception:
        messages.error(
            request,
            "Backup non ripristinato: il file è danneggiato o non è compatibile. Il database è rimasto invariato.",
        )
    return redirect("backup")
