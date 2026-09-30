"""Versioned movement interchange. JSON remains the complete financial backup."""

from collections import Counter
from datetime import time
from uuid import UUID

from django.db import transaction

from ..models import (
    Account,
    Category,
    Subcategory,
    Transaction,
    Transfer,
    KINDS,
    kind_matches_subcategory,
)
from .formatting import parse_date, parse_money
from .filters import TRANSFER_IN, TRANSFER_OUT

VERSION = "2"
HEADERS = [
    "Data",
    "Descrizione",
    "Importo",
    "Categoria",
    "Sottocategoria",
    "Tipo",
    "Saldo dopo operazione",
    "Conto o carta",
    "Note",
    "Identificativo",
    "Formato Wallet",
    "Operazione",
    "UUID operazione",
    "Conto origine",
    "Conto destinazione",
    "Orario",
    "Ordine",
    "Sequenza origine",
    "Saldo iniziale conto",
    "Saldo iniziale controconto",
    "Tipo predefinito sottocategoria",
]
REQUIRED_HEADERS = HEADERS[:-1]
TEXT_FIELDS = {
    "Descrizione",
    "Categoria",
    "Sottocategoria",
    "Conto o carta",
    "Note",
    "Identificativo",
    "Conto origine",
    "Conto destinazione",
}


def safe_cell(value):
    text = str(value)
    # Escape apostrophes too: this makes the inverse unambiguous in Wallet v2.
    return (
        "'" + text
        if text.startswith("'")
        or text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
        else text
    )


def unescape(value):
    if value.startswith("'"):
        tail = value[1:]
        if tail.startswith("'") or tail.lstrip().startswith(
            ("=", "+", "-", "@", "\t", "\r")
        ):
            return tail
    return value


def export_row(item):
    transfer = item.is_transfer
    source = item.account if not item.is_positive else item.counterparty
    destination = item.counterparty if not item.is_positive else item.account
    values = [
        item.date.strftime("%d/%m/%Y"),
        item.description,
        f"{item.signed_amount:.2f}".replace(".", ","),
        item.display_category,
        "" if transfer else item.display_subcategory,
        item.display_type,
        f"{item.balance_after:.2f}".replace(".", ","),
        item.account.name,
        item.notes,
        item.external_id,
        VERSION,
        "giroconto" if transfer else "movimento",
        str(item.uid),
        source.name if transfer else "",
        destination.name if transfer else "",
        item.operation_time.isoformat() if item.operation_time else "",
        item.order_index,
        item.event_tie // 2 if transfer else item.event_tie,
        str(item.account.initial_balance),
        str(item.counterparty.initial_balance) if transfer else "",
        "" if transfer else item.subcategory.kind,
    ]
    return [
        safe_cell(value) if name in TEXT_FIELDS else value
        for name, value in zip(HEADERS, values)
    ]


def is_wallet_csv(headers):
    return "Formato Wallet" in headers or "UUID operazione" in headers


def validate_instance(instance, foreign_keys=()):
    """Model field and domain checks without repeating known FK/unique queries.

    References are resolved from database dictionaries, identities checked in
    batches by the caller, and SQL constraints remain active during bulk_create.
    """
    instance.full_clean(
        exclude=list(foreign_keys), validate_unique=False, validate_constraints=False
    )


def _parse(raw):
    if len(raw.get("rows", [])) > 10000:
        raise ValueError("Il file contiene oltre 10.000 righe.")
    headers = raw["headers"]
    if len(headers) != len(set(headers)) or any(
        h not in headers for h in REQUIRED_HEADERS
    ):
        raise ValueError(
            "CSV Wallet incompleto: conserva tutte le colonne del file esportato."
        )
    operations, accounts, legs = {}, {}, Counter()

    def account(name, opening):
        if not name or name != name.strip() or len(name) > 100:
            raise ValueError("Nome conto vuoto, troppo lungo o con spazi esterni")
        balance = parse_money(opening)
        key = name.casefold()
        if key in accounts and accounts[key]["opening"] != balance:
            raise ValueError(f"Saldi iniziali discordanti per {name}")
        accounts.setdefault(key, {"name": name, "opening": balance})
        return key

    for number, values in enumerate(raw["rows"], 2):
        try:
            if len(values) != len(headers):
                raise ValueError("Numero di colonne diverso dall’intestazione")
            row = dict(zip(headers, map(str, values)))
            if row["Formato Wallet"] != VERSION:
                raise ValueError("Versione CSV Wallet non supportata")
            for name in TEXT_FIELDS:
                row[name] = unescape(row[name])
            op = row["Operazione"]
            if op not in {"movimento", "giroconto"}:
                raise ValueError("Operazione non riconosciuta")
            uid = str(UUID(row["UUID operazione"]))
            signed = parse_money(row["Importo"])
            if not signed:
                raise ValueError("L’importo deve essere diverso da zero")
            clock = time.fromisoformat(row["Orario"]) if row["Orario"] else None
            if clock and clock.tzinfo:
                raise ValueError("L’orario deve essere locale, senza fuso")
            order, sequence = int(row["Ordine"]), int(row["Sequenza origine"])
            if not 0 <= order <= 9223372036854775807 or sequence < 1:
                raise ValueError("Ordine o sequenza non validi")
            own = account(row["Conto o carta"], row["Saldo iniziale conto"])
            common = dict(
                uid=uid,
                operation=op,
                date=parse_date(row["Data"]),
                operation_time=clock,
                order_index=order,
                sequence=sequence,
                amount=abs(signed),
                description=row["Descrizione"],
            )
            if op == "giroconto":
                src, dst = (
                    row["Conto origine"].casefold(),
                    row["Conto destinazione"].casefold(),
                )
                if not src or not dst or src == dst or own not in {src, dst}:
                    raise ValueError(
                        "Il giroconto deve collegare due conti diversi e coerenti con la riga"
                    )
                incoming = own == dst
                expected = TRANSFER_IN if incoming else TRANSFER_OUT
                if (
                    row["Tipo"] != expected
                    or (signed > 0) != incoming
                    or row["Categoria"] != "Giroconto"
                    or row["Sottocategoria"]
                ):
                    raise ValueError(
                        "Segno, tipo o categoria del giroconto non coerenti"
                    )
                if row["Note"] or row["Identificativo"] != f"giroconto:{uid}":
                    raise ValueError("Note o identificativo del giroconto non validi")
                opposite = (
                    row["Conto origine"] if incoming else row["Conto destinazione"]
                )
                account(opposite, row["Saldo iniziale controconto"])
                common.update(source=src, destination=dst)
                legs[(uid, own)] += 1
            else:
                if row["Tipo"] not in dict(KINDS) or (signed > 0) != (
                    row["Tipo"] == "Entrata"
                ):
                    raise ValueError("Segno e tipo del movimento non coerenti")
                if (
                    row["Conto origine"]
                    or row["Conto destinazione"]
                    or row["Saldo iniziale controconto"]
                ):
                    raise ValueError(
                        "Un movimento ordinario non può avere conti di giroconto"
                    )
                if not row["Categoria"] or not row["Sottocategoria"]:
                    raise ValueError("Categoria e sottocategoria richieste")
                default_kind = row.get("Tipo predefinito sottocategoria", row["Tipo"])
                if default_kind not in dict(KINDS) or not kind_matches_subcategory(
                    row["Tipo"], default_kind
                ):
                    raise ValueError(
                        "Tipo del movimento incompatibile con il tipo predefinito della sottocategoria"
                    )
                common.update(
                    subcategory_kind=default_kind,
                    explicit_subcategory_kind="Tipo predefinito sottocategoria" in row,
                    account=own,
                    category=row["Categoria"],
                    subcategory=row["Sottocategoria"],
                    kind=row["Tipo"],
                    notes=row["Note"],
                    external_id=row["Identificativo"],
                )
            if uid in operations and common != operations[uid]:
                raise ValueError("UUID ripetuto con dati discordanti")
            operations[uid] = common
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"Riga {number}: {exc}") from exc
    if not operations:
        raise ValueError("Il CSV non contiene operazioni.")
    return (
        sorted(
            operations.values(),
            key=lambda r: (
                r["date"],
                r["operation_time"] or time.min,
                r["order_index"],
                r["sequence"],
            ),
        ),
        accounts,
        legs,
    )


def _uid_map(model, uids):
    found = {}
    for offset in range(0, len(uids), 400):
        found.update(
            {
                str(x.uid): x
                for x in model.objects.filter(uid__in=uids[offset : offset + 400])
            }
        )
    return found


def import_wallet_csv(raw, *, commit=False):
    """Validate a complete batch; preview and confirmation share the same path."""
    with transaction.atomic():
        operations, account_specs, legs = _parse(raw)
        existing_accounts = {}
        for obj in Account.objects.all():
            key = obj.name.casefold()
            if key in existing_accounts:
                raise ValueError(
                    f"Due conti hanno lo stesso nome ignorando maiuscole/minuscole: {obj.name}"
                )
            existing_accounts[key] = obj
        accounts, new_accounts, balance_warnings = {}, [], []
        for key, spec in account_specs.items():
            obj = existing_accounts.get(key)
            if obj is None:
                obj = Account(name=spec["name"], initial_balance=spec["opening"])
                validate_instance(obj)
                new_accounts.append(obj)
            elif obj.initial_balance != spec["opening"]:
                balance_warnings.append(obj.name)
            accounts[key] = obj
        categories = {x.name: x for x in Category.objects.all()}
        subs = {
            (s.category.name, s.name): s
            for s in Subcategory.objects.select_related("category")
        }
        new_cats, new_subs = [], []
        for row in operations:
            if row["operation"] != "movimento":
                continue
            name, subname = row["category"], row["subcategory"]
            if name not in categories:
                cat = Category(name=name)
                validate_instance(cat)
                categories[name] = cat
                new_cats.append(cat)
            key = (name, subname)
            if key not in subs:
                sub = Subcategory(
                    category=categories[name],
                    name=subname,
                    kind=row["subcategory_kind"],
                )
                validate_instance(sub, ("category",))
                subs[key] = sub
                new_subs.append(sub)
            elif (
                row["explicit_subcategory_kind"]
                and subs[key].kind != row["subcategory_kind"]
            ) or not kind_matches_subcategory(row["kind"], subs[key].kind):
                raise ValueError(
                    f"Tipo incompatibile per {name} · {subname}; nessun dato modificato."
                )

        if commit:
            Account.objects.bulk_create(new_accounts, batch_size=400)
            Category.objects.bulk_create(new_cats, batch_size=400)
            # Assign newly generated FK IDs before insertion.
            for sub in new_subs:
                sub.category_id = sub.category.pk
            Subcategory.objects.bulk_create(new_subs, batch_size=400)

        uids = [r["uid"] for r in operations]
        tx_existing, tr_existing = _uid_map(Transaction, uids), _uid_map(Transfer, uids)
        external = {}
        needed_external = list(
            {r.get("external_id") for r in operations if r.get("external_id")}
        )
        for offset in range(0, len(needed_external), 400):
            external.update(
                {
                    (t.account_id, t.external_id): str(t.uid)
                    for t in Transaction.objects.filter(
                        external_id__in=needed_external[offset : offset + 400],
                        account_id__in=[a.pk for a in accounts.values() if a.pk],
                    )
                }
            )
        additions, transfers, duplicates, preview = [], [], 0, []
        seen_external = set()
        for row in operations:
            is_transfer = row["operation"] == "giroconto"
            fields = {
                k: row[k]
                for k in (
                    "uid",
                    "date",
                    "operation_time",
                    "order_index",
                    "amount",
                    "description",
                )
            }
            if is_transfer:
                obj = Transfer(
                    **fields,
                    source=accounts[row["source"]],
                    destination=accounts[row["destination"]],
                )
                validate_instance(obj, ("source", "destination"))
                existing, wrong = tr_existing.get(row["uid"]), tx_existing.get(
                    row["uid"]
                )
                compare = (
                    "date",
                    "operation_time",
                    "order_index",
                    "amount",
                    "description",
                    "source_id",
                    "destination_id",
                )
                label = f"{obj.source.name} → {obj.destination.name}"
            else:
                obj = Transaction(
                    **fields,
                    account=accounts[row["account"]],
                    subcategory=subs[(row["category"], row["subcategory"])],
                    kind=row["kind"],
                    notes=row["notes"],
                    external_id=row["external_id"],
                )
                validate_instance(obj, ("account", "subcategory"))
                existing, wrong = tx_existing.get(row["uid"]), tr_existing.get(
                    row["uid"]
                )
                compare = (
                    "date",
                    "operation_time",
                    "order_index",
                    "amount",
                    "description",
                    "account_id",
                    "subcategory_id",
                    "kind",
                    "notes",
                    "external_id",
                )
                label = obj.account.name
                if obj.external_id:
                    key = (row["account"], obj.external_id)
                    old_uid = external.get((obj.account_id, obj.external_id))
                    if key in seen_external or (old_uid and old_uid != row["uid"]):
                        raise ValueError(
                            f"Identificativo esterno in conflitto: {obj.external_id}"
                        )
                    seen_external.add(key)
            if wrong or (
                existing
                and any(getattr(existing, key) != getattr(obj, key) for key in compare)
            ):
                raise ValueError(
                    f"UUID {row['uid']} già presente con dati diversi: nessuna operazione sovrascritta."
                )
            if existing:
                duplicates += 1
            else:
                (transfers if is_transfer else additions).append(obj)
            if len(preview) < 100:
                preview.append(
                    dict(
                        date=obj.date,
                        description=obj.description,
                        amount=obj.amount,
                        account=label,
                        kind="Giroconto" if is_transfer else obj.kind,
                        duplicate=bool(existing),
                    )
                )
        if commit:
            Transaction.objects.bulk_create(additions, batch_size=400)
            Transfer.objects.bulk_create(transfers, batch_size=400)
        return dict(
            added=len(additions) + len(transfers),
            movements=len(additions),
            transfers=len(transfers),
            duplicates=duplicates,
            to_fix=0,
            balance_warnings=len(balance_warnings),
            balance_accounts=balance_warnings,
            rows=preview,
            source_rows=len(raw["rows"]),
            operation_count=len(operations),
            single_legs=sum(
                1
                for r in operations
                if r["operation"] == "giroconto"
                and sum((r["uid"], k) in legs for k in (r["source"], r["destination"]))
                == 1
            ),
            new_accounts=[a.name for a in new_accounts],
            new_categories=len(new_cats),
            new_subcategories=len(new_subs),
        )
