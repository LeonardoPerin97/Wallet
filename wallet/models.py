import uuid
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models

KINDS = [
    ("Entrata", "Entrata"),
    ("Uscita necessaria", "Uscita necessaria"),
    ("Uscita extra", "Uscita extra"),
    ("Investimento", "Investimento"),
]
OUTGOING = {"Uscita necessaria", "Uscita extra", "Investimento"}
FLEXIBLE_EXPENSE_KINDS = {"Uscita necessaria", "Uscita extra"}


def kind_matches_subcategory(kind, default_kind):
    return kind == default_kind or (
        kind in FLEXIBLE_EXPENSE_KINDS and default_kind in FLEXIBLE_EXPENSE_KINDS
    )


class Category(models.Model):
    name = models.CharField("categoria", max_length=100, unique=True)
    color = models.CharField("colore", max_length=7, default="#64748B")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "categoria"
        verbose_name_plural = "categorie"

    def __str__(self):
        return self.name


class Subcategory(models.Model):
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="subcategories"
    )
    name = models.CharField("sottocategoria", max_length=100)
    kind = models.CharField("tipo", max_length=30, choices=KINDS)
    # Icon identifier used by the transaction list. The glyph registry lives in
    # the presentation layer; the identifier keeps each subcategory configurable.
    icon = models.CharField("icona", max_length=40, default="tag", blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "name"], name="unique_subcategory_name_per_category"
            )
        ]
        verbose_name = "sottocategoria"
        verbose_name_plural = "sottocategorie"

    def __str__(self):
        return f"{self.category.name} · {self.name}"


class Account(models.Model):
    name = models.CharField("conto o carta", max_length=100, unique=True)
    account_type = models.CharField(
        "tipo",
        max_length=20,
        default="conto",
        choices=[
            ("conto", "Conto corrente"),
            ("carta", "Carta"),
            ("risparmio", "Risparmio"),
            ("contanti", "Contanti"),
        ],
    )
    initial_balance = models.DecimalField(
        "saldo iniziale", max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "conto"
        verbose_name_plural = "conti e carte"

    def __str__(self):
        return self.name


class Transaction(models.Model):
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    date = models.DateField("data")
    operation_time = models.TimeField("orario", null=True, blank=True)
    order_index = models.PositiveBigIntegerField(default=0, db_index=True)
    description = models.CharField("descrizione", max_length=250, blank=True)
    amount = models.DecimalField("importo", max_digits=14, decimal_places=2)
    subcategory = models.ForeignKey(
        Subcategory, on_delete=models.PROTECT, related_name="transactions"
    )
    kind = models.CharField("tipo", max_length=30, choices=KINDS)
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="transactions"
    )
    notes = models.TextField(blank=True)
    external_id = models.CharField(max_length=150, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-operation_time", "-order_index", "-id"]
        indexes = [
            models.Index(
                fields=["date", "operation_time", "order_index", "id"],
                name="wallet_tx_ledger_order",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="transaction_amount_positive"
            ),
            models.UniqueConstraint(
                fields=["account", "external_id"],
                condition=~models.Q(external_id=""),
                name="unique_external_transaction_id_per_account",
            ),
        ]
        verbose_name = "movimento"
        verbose_name_plural = "movimenti"

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError(
                {
                    "amount": "L’importo deve essere positivo; il segno è determinato dal tipo."
                }
            )
        if self.subcategory_id and not kind_matches_subcategory(
            self.kind, self.subcategory.kind
        ):
            raise ValidationError(
                {
                    "kind": "Il tipo deve corrispondere alla sottocategoria; per le spese puoi scegliere Necessaria o Extra."
                }
            )

    def save(self, *args, **kwargs):
        if self.subcategory_id and not self.kind:
            self.kind = self.subcategory.kind
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def signed_amount(self):
        return self.amount if self.kind == "Entrata" else -self.amount

    @property
    def category(self):
        return self.subcategory.category

    def __str__(self):
        return f"{self.date:%d/%m/%Y} · {self.description}"


class Transfer(models.Model):
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    date = models.DateField()
    operation_time = models.TimeField(null=True, blank=True)
    order_index = models.PositiveBigIntegerField(default=0, db_index=True)
    source = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="transfers_out"
    )
    destination = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="transfers_in"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.CharField(max_length=200, default="Giroconto")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-order_index", "-id"]
        indexes = [
            models.Index(
                fields=["date", "operation_time", "order_index", "id"],
                name="wallet_transfer_ledger_order",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="transfer_amount_positive"
            )
        ]

    def clean(self):
        errors = {}
        if self.source_id and self.source_id == self.destination_id:
            errors["destination"] = "Seleziona due conti diversi."
        if self.amount is not None and self.amount <= 0:
            errors["amount"] = "L’importo deve essere maggiore di zero."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.description}: {self.source} → {self.destination}"


class UserPreference(models.Model):
    """Single-user preferences for this local wallet instance."""

    account = models.ForeignKey(
        Account, null=True, blank=True, on_delete=models.SET_NULL
    )
    accounts = models.ManyToManyField(
        Account, blank=True, related_name="dashboard_preferences"
    )
    categories = models.ManyToManyField(
        Category, blank=True, related_name="dashboard_preferences"
    )
    no_accounts_selected = models.BooleanField(default=False)
    no_categories_selected = models.BooleanField(default=False)
    all_categories_selected = models.BooleanField(default=True)
    include_transfers = models.BooleanField(default=True)
    period = models.CharField(max_length=12, default="tutto")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "preferenza"
        verbose_name_plural = "preferenze"


class CategoryBudget(models.Model):
    """Monthly spending limit for one expense category."""

    month = models.DateField("mese", help_text="Usare il primo giorno del mese.")
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="monthly_budgets"
    )
    amount = models.DecimalField(
        "budget mensile", max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["month", "category"], name="unique_budget_category_month"
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gte=0), name="budget_amount_nonnegative"
            ),
        ]
        verbose_name = "budget mensile"
        verbose_name_plural = "budget mensili"

    def clean(self):
        if self.month and self.month.day != 1:
            raise ValidationError(
                {"month": "La data del budget deve essere il primo giorno del mese."}
            )
        if self.amount is not None and self.amount < 0:
            raise ValidationError({"amount": "Il budget non può essere negativo."})
        if (
            self.category_id
            and self.month
            and SubcategoryBudget.objects.filter(
                month=self.month, subcategory__category_id=self.category_id
            ).exists()
        ):
            raise ValidationError(
                "Questa categoria ha già budget per sottocategoria nel mese: usa la loro somma."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.category.name} · {self.month:%m/%Y}"


class SubcategoryBudget(models.Model):
    """Monthly line item; category totals are calculated, never stored twice."""

    month = models.DateField("mese", help_text="Usare il primo giorno del mese.")
    subcategory = models.ForeignKey(
        Subcategory, on_delete=models.PROTECT, related_name="monthly_budgets"
    )
    amount = models.DecimalField(
        "budget mensile", max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["subcategory__category__name", "subcategory__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["month", "subcategory"], name="unique_budget_subcategory_month"
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gte=0), name="sub_budget_amount_nonnegative"
            ),
        ]
        verbose_name = "budget sottocategoria"
        verbose_name_plural = "budget sottocategorie"

    def clean(self):
        if self.month and self.month.day != 1:
            raise ValidationError(
                {"month": "La data del budget deve essere il primo giorno del mese."}
            )
        if self.amount is not None and self.amount < 0:
            raise ValidationError({"amount": "Il budget non può essere negativo."})
        if self.subcategory_id:
            if self.subcategory.kind not in OUTGOING:
                raise ValidationError(
                    {"subcategory": "Scegli una sottocategoria di uscita."}
                )
            if (
                self.month
                and CategoryBudget.objects.filter(
                    month=self.month, category_id=self.subcategory.category_id
                ).exists()
            ):
                raise ValidationError(
                    "Rimuovi il limite unico della categoria prima di suddividerlo."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subcategory} · {self.month:%m/%Y}"
