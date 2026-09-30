"""Reproducible SQLite benchmark on synthetic data in a disposable database.

Run: python scripts/benchmark_wallet.py --sizes 10000 50000 --output result.json
No personal database or environment database URL is used.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]


def worker(size):
    selected = Path(os.environ.get("WALLET_DB_PATH", "")).resolve()
    if (
        os.environ.get("WALLET_BENCHMARK_WORKER") != "1"
        or selected == (ROOT / "wallet.sqlite3").resolve()
        or selected.exists()
        or os.environ.get("DATABASE_URL")
        or os.environ.get("POSTGRES_URI")
    ):
        raise RuntimeError(
            "Il benchmark richiede un database temporaneo nuovo creato dal processo principale."
        )
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wallet_project.settings")
    import django

    django.setup()
    from datetime import date, timedelta
    from decimal import Decimal
    from django.core.management import call_command
    from django.core.paginator import Paginator
    from django.db import connection
    from django.http import QueryDict
    from django.test.utils import CaptureQueriesContext
    from wallet.models import Account, Category, Subcategory, Transaction, Transfer
    from wallet.services.analytics import analytics
    from wallet.services.filters import Filters
    from wallet.services.movements import movement_rows, list_groups

    call_command("migrate", verbosity=0)
    accounts = [
        Account.objects.create(name=f"Benchmark {i}", initial_balance=1000)
        for i in range(3)
    ]
    cat = Category.objects.create(name="Benchmark")
    subs = [
        Subcategory.objects.create(category=cat, name=kind, kind=kind)
        for kind in ("Entrata", "Uscita extra", "Uscita necessaria")
    ]
    Transaction.objects.bulk_create(
        [
            Transaction(
                date=date(2023, 1, 1) + timedelta(days=i % 1095),
                amount=Decimal((i % 9999) + 1) / 100,
                account=accounts[i % 3],
                subcategory=subs[i % 3],
                kind=subs[i % 3].kind,
                order_index=i + 1,
                description=f"Operazione {i}",
                external_id=f"benchmark-{i}",
            )
            for i in range(size)
        ],
        batch_size=500,
    )
    Transfer.objects.bulk_create(
        [
            Transfer(
                date=date(2023, 1, 1) + timedelta(days=i % 1095),
                amount=Decimal("15.23"),
                source=accounts[i % 3],
                destination=accounts[(i + 1) % 3],
                order_index=size + i + 1,
            )
            for i in range(size // 10)
        ],
        batch_size=500,
    )
    filters = Filters.parse(
        QueryDict("periodo=custom&inizio=01/01/2023&fine=31/12/2025")
    )

    def register():
        rows, _ = movement_rows(filters)
        page = Paginator(rows, 25).get_page(1)
        visible = list(page.object_list)
        list_groups(rows, visible)
        return {"count": page.paginator.count, "visible": len(visible)}

    def home():
        data = analytics(filters, with_balance=True)
        return {k: str(data[k]) for k in ("income", "outgoing", "opening", "closing")}

    result = {
        "transactions": size,
        "transfers": size // 10,
        "database": "SQLite",
        "python": sys.version.split()[0],
        "django": django.get_version(),
    }
    for name, fn in (("register_page_25", register), ("home", home)):
        tracemalloc.start()
        with CaptureQueriesContext(connection) as queries:
            started = time.perf_counter()
            check = fn()
            elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result[name] = {
            "seconds": round(elapsed, 4),
            "python_peak_mib": round(peak / 1024**2, 3),
            "queries": len(queries),
            "check": check,
        }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[10000, 50000])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker)))
    else:
        results = []
        for size in args.sizes:
            if size < 1:
                parser.error("Le dimensioni devono essere positive")
            with tempfile.TemporaryDirectory(prefix="wallet-benchmark-") as directory:
                env = dict(
                    os.environ,
                    WALLET_DB_PATH=str(Path(directory) / "benchmark.sqlite3"),
                    WALLET_DEBUG="1",
                    WALLET_BENCHMARK_WORKER="1",
                )
                for key in (
                    "DATABASE_URL",
                    "POSTGRES_URI",
                    "WALLET_ENV",
                    "DJANGO_SETTINGS_MODULE",
                ):
                    env.pop(key, None)
                run = subprocess.run(
                    [sys.executable, __file__, "--worker", str(size)],
                    env=env,
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=True,
                )
                results.append(json.loads(run.stdout))
                print(json.dumps(results[-1], indent=2), flush=True)
        if args.output:
            args.output.write_text(json.dumps(results, indent=2) + "\n")
