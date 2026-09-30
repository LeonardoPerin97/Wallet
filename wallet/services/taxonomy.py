import csv
import io
import re
from django.db import transaction as db_transaction
from ..models import Category


@db_transaction.atomic
def import_taxonomy(file_obj):
    """Upsert the CSV taxonomy. Old rows are archived, never deleted."""
    content = file_obj.read()
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    names = {name.strip().lstrip("\ufeff") for name in (reader.fieldnames or [])}
    canonical_columns = {
        "Categoria": "Categoria",
        "Sottocategoria": "Sottocategoria",
        "Colore": "Colore",
        "Tipo": "Tipo",
    }
    bilingual_columns = {
        "Categoria": "Category_IT",
        "Sottocategoria": "Subcategory_IT",
        "Colore": "Color",
        "Tipo": "Type_IT",
    }
    if set(canonical_columns.values()).issubset(names):
        columns = canonical_columns
    elif set(bilingual_columns.values()).issubset(names):
        columns = bilingual_columns
    else:
        raise ValueError(
            "Il CSV deve contenere Categoria, Sottocategoria, Colore e Tipo "
            "oppure Category_IT, Subcategory_IT, Color e Type_IT."
        )
    rows = []
    for raw in reader:
        normalized = {
            key.strip().lstrip("\ufeff"): value for key, value in raw.items() if key
        }
        clean = {
            key: (normalized.get(column) or "").strip()
            for key, column in columns.items()
        }
        required = set(columns)
        if not any(clean.values()):
            continue
        if not all(clean.get(k) for k in required):
            raise ValueError(
                f"Riga {reader.line_num} incompleta: nessuna categoria è stata modificata."
            )
        if clean["Tipo"] not in {
            "Entrata",
            "Uscita necessaria",
            "Uscita extra",
            "Investimento",
        }:
            raise ValueError(f"Tipo non riconosciuto nel CSV: {clean['Tipo']}")
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", clean["Colore"]):
            raise ValueError(f"Colore non valido per {clean['Categoria']}.")
        rows.append(clean)
    if not rows:
        raise ValueError("Il CSV non contiene righe valide.")
    from ..models import Subcategory

    for row in rows:
        previous = Subcategory.objects.filter(
            category__name=row["Categoria"], name=row["Sottocategoria"]
        ).first()
        if (
            previous
            and previous.kind != row["Tipo"]
            and (previous.transactions.exists() or previous.monthly_budgets.exists())
        ):
            raise ValueError(
                f"Il tipo di {previous} è già usato nello storico: crea una nuova sottocategoria."
            )
    Category.objects.update(active=False)
    from ..models import Subcategory

    Subcategory.objects.update(active=False)
    for row in rows:
        category, _ = Category.objects.update_or_create(
            name=row["Categoria"], defaults={"color": row["Colore"], "active": True}
        )
        Subcategory.objects.update_or_create(
            category=category,
            name=row["Sottocategoria"],
            defaults={"kind": row["Tipo"], "active": True},
        )
    return len(rows)
