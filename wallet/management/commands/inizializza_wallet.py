from pathlib import Path
from django.core.management.base import BaseCommand
from wallet.models import Account, Category
from wallet.services import import_taxonomy


class Command(BaseCommand):
    help = "Carica le categorie iniziali e crea il conto predefinito se necessario."

    def handle(self, *args, **options):
        if not Category.objects.exists():
            path = Path(__file__).resolve().parents[2] / "categorie_movimenti.csv"
            with path.open("rb") as f:
                count = import_taxonomy(f)
            self.stdout.write(
                self.style.SUCCESS(f"Caricate {count} sottocategorie dalla tassonomia.")
            )
        else:
            self.stdout.write(
                "La tassonomia è già presente; nessuna categoria modificata."
            )
        if not Account.objects.exists():
            Account.objects.create(name="Conto principale")
            self.stdout.write(
                self.style.SUCCESS(
                    "Creato il conto iniziale «Conto principale» con saldo 0,00 €."
                )
            )
        else:
            self.stdout.write("I conti esistenti sono stati mantenuti.")
