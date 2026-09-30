"""Avvia la demo locale senza aprire o modificare il database personale."""

import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reset-password", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    database = root / "demo" / "wallet_demo.sqlite3"
    database.parent.mkdir(exist_ok=True)
    for key in ("DATABASE_URL", "POSTGRES_URI"):
        os.environ.pop(key, None)
    os.environ.update(
        WALLET_ENV="local",
        WALLET_DEBUG="1",
        WALLET_DB_PATH=str(database),
        WALLET_OWNER_USERNAME="demo",
        WALLET_ALLOWED_HOSTS="127.0.0.1,localhost",
        DJANGO_SETTINGS_MODULE="wallet_project.settings",
    )
    try:
        import django
    except ImportError:
        parser.exit(
            1,
            "Installa prima le dipendenze: python -m pip install -r requirements.txt\n",
        )
    django.setup()
    from django.contrib.auth import get_user_model
    from django.core.management import call_command

    call_command("migrate", interactive=False, verbosity=0)
    user_model = get_user_model()
    if not user_model.objects.exists():
        call_command("crea_demo")
    user = user_model.objects.filter(username="demo").first()
    if user is None:
        parser.exit(
            1, "Il database demo non contiene l'utente demo. Consulta il README.\n"
        )
    if args.reset_password or not user.has_usable_password():
        print("Scegli una password per l'utente demo (almeno 12 caratteri).")
        call_command("changepassword", "demo")
    print(f"\nDemo pronta: http://127.0.0.1:{args.port}/ — utente: demo")
    print(
        "Il database personale wallet.sqlite3 è separato. Ctrl+C per fermare il server.\n"
    )
    call_command("runserver", f"127.0.0.1:{args.port}", use_reloader=False)


if __name__ == "__main__":
    main()
