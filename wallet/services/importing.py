from collections import defaultdict
from decimal import Decimal
from ..models import Account, Subcategory, Transaction
from . import ZERO, parse_date, parse_money
from .import_duplicates import duplicate_index, signature

FIELD_LABELS = [
    ("date", "Data", ["data", "date"]),
    (
        "description",
        "Descrizione",
        ["descrizione", "description", "causale", "operazione", "dettaglio"],
    ),
    ("amount", "Importo", ["importo", "amount"]),
    (
        "income",
        "Entrate (colonna separata)",
        ["accredito", "entrate", "income", "credit"],
    ),
    (
        "expense",
        "Uscite (colonna separata)",
        ["addebito", "uscite", "expense", "debit"],
    ),
    ("account", "Conto o carta", ["conto", "carta", "account", "card"]),
    ("category", "Categoria", ["categoria", "category"]),
    ("subcategory", "Sottocategoria", ["sottocategoria", "subcategory"]),
    ("type", "Tipo", ["tipo", "type", "entratauscita"]),
    ("balance", "Saldo dopo operazione", ["saldo", "balance"]),
    (
        "external_id",
        "Identificativo",
        ["identificativo", "riferimento", "transactionid", "id movimento"],
    ),
    (
        "direction",
        "Entrata/uscita",
        ["direzione", "verso", "entratauscita", "movimento"],
    ),
    ("time", "Orario (facoltativo)", ["ora", "orario", "time"]),
    ("notes", "Note", ["note", "memo"]),
]


def _raw_col(row, mapping, field):
    index = mapping.get(field)
    return (
        row[int(index)] if str(index).isdigit() and 0 <= int(index) < len(row) else ""
    )


def _analyze_import(raw, mapping, date_format=""):
    source_rows = raw["rows"]
    analyzed = []
    all_subs = list(
        Subcategory.objects.select_related("category").filter(
            active=True, category__active=True
        )
    )
    sub_lookup = {(s.category.name.casefold(), s.name.casefold()): s for s in all_subs}
    by_sub = defaultdict(list)
    for subcategory in all_subs:
        by_sub[subcategory.name.casefold()].append(subcategory)
    known_accounts = {a.name.casefold(): a.id for a in Account.objects.all()}
    for i, row in enumerate(source_rows):
        item = {
            "row": i,
            "raw": [str(v if v is not None else "") for v in row],
            "status": "ok",
            "errors": [],
            "warnings": [],
        }
        try:
            item["date"] = parse_date(
                _raw_col(row, mapping, "date"), date_format
            ).isoformat()
        except Exception as e:
            item["date"] = ""
            item["errors"].append(f"Data: {e}")
        item["description"] = str(_raw_col(row, mapping, "description") or "").strip()
        item["notes"] = str(_raw_col(row, mapping, "notes") or "")

        try:
            if mapping.get("amount") not in (None, ""):
                raw_amount = parse_money(_raw_col(row, mapping, "amount"))
            else:
                income_text, expense_text = _raw_col(row, mapping, "income"), _raw_col(
                    row, mapping, "expense"
                )
                income_amount = (
                    parse_money(income_text) if str(income_text or "").strip() else ZERO
                )
                expense_amount = (
                    parse_money(expense_text)
                    if str(expense_text or "").strip()
                    else ZERO
                )
                if income_amount and expense_amount:
                    raise ValueError("entrate e uscite sono entrambe valorizzate")
                if not income_amount and not expense_amount:
                    raise ValueError("nessun importo trovato")
                raw_amount = income_amount if income_amount else -abs(expense_amount)
            item["amount"] = str(abs(raw_amount))
        except Exception as e:
            raw_amount = None
            item["amount"] = ""
            item["errors"].append(f"Importo: {e}")
        item["source_sign"] = -1 if raw_amount is not None and raw_amount < 0 else 1
        item["account_name"] = str(_raw_col(row, mapping, "account") or "").strip()
        item["operation_time"] = ""
        time_text = str(_raw_col(row, mapping, "time") or "").strip()
        if time_text:
            import datetime as dt

            time_text = time_text.rsplit(" ", 1)[-1]
            for fmt in ("%H:%M:%S", "%H:%M"):
                try:
                    item["operation_time"] = dt.datetime.strptime(
                        time_text, fmt
                    ).strftime("%H:%M:%S")
                    break
                except ValueError:
                    pass
            if not item["operation_time"]:
                item["warnings"].append(
                    "Orario non riconosciuto; per questa riga verrà mantenuto l’ordine del file."
                )
        item["external_id"] = str(_raw_col(row, mapping, "external_id") or "").strip()
        item["balance"] = ""
        if mapping.get("balance") not in (None, ""):
            try:
                item["balance"] = str(parse_money(_raw_col(row, mapping, "balance")))
            except Exception as e:
                item["warnings"].append(f"Saldo progressivo non letto: {e}")
        category = str(_raw_col(row, mapping, "category") or "").strip()
        subname = str(_raw_col(row, mapping, "subcategory") or "").strip()
        candidates = by_sub.get(subname.casefold(), [])
        sub = (
            sub_lookup.get((category.casefold(), subname.casefold()))
            if category and subname
            else (candidates[0] if len(candidates) == 1 else None)
        )
        if sub:
            item.update(
                {
                    "subcategory_id": sub.id,
                    "category_name": sub.category.name,
                    "subcategory_name": sub.name,
                    "kind": sub.kind,
                }
            )
            source_type = str(_raw_col(row, mapping, "type") or "").strip()
            if source_type and source_type.casefold() != sub.kind.casefold():
                item["warnings"].append(
                    f"Tipo nel file «{source_type}» diverso dalla tassonomia; verrà usato «{sub.kind}»."
                )
            direction = (
                str(_raw_col(row, mapping, "direction") or "").strip().casefold()
            )
            is_income = any(
                x in direction for x in ("entrata", "accredito", "income", "credit")
            )
            is_expense = any(
                x in direction for x in ("uscita", "addebito", "expense", "debit")
            )
            if (is_income and sub.kind != "Entrata") or (
                is_expense and sub.kind == "Entrata"
            ):
                item["warnings"].append(
                    "La direzione del file non coincide con il tipo della sottocategoria."
                )
        else:
            item.update(
                {
                    "subcategory_id": "",
                    "category_name": category,
                    "subcategory_name": subname,
                    "kind": "",
                }
            )
            item["errors"].append(
                "Sottocategoria presente in più categorie; seleziona la voce corretta."
                if not category and len(candidates) > 1
                else "Categoria/sottocategoria non riconosciuta: assegnala prima di importare."
            )
        if item["errors"]:
            item["status"] = "correggere"
        analyzed.append(item)
    specs = [
        (
            known_accounts.get(r["account_name"].casefold()),
            parse_date(r["date"]),
            r["description"],
            Decimal(r["amount"]),
            r["external_id"],
        )
        for r in analyzed
        if r["date"] and r["amount"] and r["account_name"] and r["subcategory_id"]
    ]
    external_ids, signatures = duplicate_index(specs)
    for item in analyzed:
        if not item["date"] or not item["amount"] or item["status"] != "ok":
            continue
        acc = known_accounts.get(item["account_name"].casefold())
        if acc and item["external_id"] and (acc, item["external_id"]) in external_ids:
            item["status"] = "duplicato"
            item["duplicate_reason"] = "Identificativo già importato"
        elif (
            signature(
                acc,
                parse_date(item["date"]),
                item["description"],
                Decimal(item["amount"]),
            )
            in signatures
        ):
            item["status"] = "duplicato"
            item["duplicate_reason"] = (
                "Data, descrizione, importo e conto/carta coincidono"
            )
    return analyzed


def import_review_context(rows, mapping):
    """Build a review in bounded queries, including partially supplied balances."""
    from django.db.models import Exists, OuterRef
    from ..models import Transfer
    from .ledger import balance_before

    accounts = {
        a.name.casefold(): a
        for a in Account.objects.annotate(
            has_transactions=Exists(
                Transaction.objects.filter(account_id=OuterRef("pk"))
            ),
            has_transfers_out=Exists(Transfer.objects.filter(source_id=OuterRef("pk"))),
            has_transfers_in=Exists(
                Transfer.objects.filter(destination_id=OuterRef("pk"))
            ),
        )
    }
    subs = list(
        Subcategory.objects.filter(active=True, category__active=True).select_related(
            "category"
        )
    )
    sub_by_id = {str(s.id): s for s in subs}
    cumulative = defaultdict(lambda: ZERO)
    inferences, dates = defaultdict(list), defaultdict(list)
    names = list(
        dict.fromkeys(r["account_name"] for r in rows if r.get("account_name"))
    )
    prepared = []
    for row in rows:
        sub = sub_by_id.get(str(row.get("subcategory_id", "")))
        if not sub or not row.get("account_name"):
            continue
        try:
            day, amount = parse_date(row["date"]), abs(parse_money(row["amount"]))
        except (ValueError, TypeError, KeyError):
            continue
        prepared.append(
            (day, row.get("operation_time") or "00:00:00", row["row"], row, sub, amount)
        )
    for day, _, _, row, sub, amount in sorted(prepared, key=lambda item: item[:3]):
        name = row["account_name"]
        dates[name].append(day)
        cumulative[name] += amount if sub.kind == "Entrata" else -amount
        if mapping.get("balance") not in (None, "") and row.get("balance") not in (
            None,
            "",
        ):
            try:
                inferences[name].append(parse_money(row["balance"]) - cumulative[name])
            except (ValueError, TypeError):
                pass  # The row remains visible with its validation errors.

    checks, new_accounts, opening_accounts = {}, [], []
    for name in names:
        account = accounts.get(name.casefold())
        has_ledger = bool(
            account
            and (
                account.has_transactions
                or account.has_transfers_out
                or account.has_transfers_in
            )
        )
        vals = inferences.get(name, [])
        if not account:
            new_accounts.append(name)
            opening_accounts.append(name)
        elif not has_ledger and account.initial_balance == ZERO and not vals:
            opening_accounts.append(name)
        if not vals:
            continue
        check = dict(
            opening=vals[0],
            consistent=all(abs(v - vals[0]) <= Decimal("0.01") for v in vals),
            count=len(vals),
            existing=bool(account),
            matches_existing=None,
            existing_balance=None,
            will_set=False,
        )
        if account:
            if not has_ledger and account.initial_balance == ZERO:
                check["will_set"] = True
            else:
                existing = (
                    balance_before(min(dates[name]), {account.id})
                    if has_ledger
                    else account.initial_balance
                )
                check.update(
                    existing_balance=existing,
                    matches_existing=abs(existing - vals[0]) <= Decimal("0.01"),
                )
        checks[name] = check
    return {
        "rows": rows,
        "ok_count": sum(r["status"] == "ok" for r in rows),
        "duplicate_count": sum(r["status"] == "duplicato" for r in rows),
        "repair_count": sum(r["status"] == "correggere" for r in rows),
        "subcategories": subs,
        "new_accounts": new_accounts,
        "opening_accounts": opening_accounts,
        "balance_checks": checks,
        "has_balance": mapping.get("balance") not in (None, ""),
        "default_balance": "0,00",
    }
