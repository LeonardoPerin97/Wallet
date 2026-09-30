from decimal import Decimal
from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.exceptions import ValidationError
from .models import (
    Account,
    Category,
    Subcategory,
    Transaction,
    Transfer,
    FLEXIBLE_EXPENSE_KINDS,
)
from .access import is_wallet_owner


class ItalianMoneyField(forms.DecimalField):
    """Accept both 1.234,56 and 1234.56 without rounding or float conversion."""

    def to_python(self, value):
        if value in self.empty_values:
            return None
        from .services import parse_money

        try:
            return parse_money(value)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def prepare_value(self, value):
        return f"{value:.2f}".replace(".", ",") if isinstance(value, Decimal) else value


class WalletAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Nome utente"
        self.fields["username"].widget.attrs.update(
            {"autocomplete": "username", "autofocus": True}
        )
        self.fields["password"].label = "Password"
        self.fields["password"].widget.attrs.update(
            {"autocomplete": "current-password"}
        )

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not is_wallet_owner(user):
            raise ValidationError(
                "Questo account non è autorizzato ad accedere a questo wallet.",
                code="wallet_owner_required",
            )


class WalletPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Password attuale"
        self.fields["new_password1"].label = "Nuova password"
        self.fields["new_password2"].label = "Conferma nuova password"


class TransactionForm(forms.ModelForm):
    expense_kind = forms.ChoiceField(
        label="Tipo di uscita",
        required=False,
        choices=[("Uscita necessaria", "Necessaria"), ("Uscita extra", "Extra")],
        widget=forms.RadioSelect,
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(active=True), label="Categoria"
    )
    date = forms.DateField(
        label="Data",
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        localize=False,
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    amount = ItalianMoneyField(
        label="Importo (€)",
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={"step": "0.01", "placeholder": "0,00"}),
    )

    class Meta:
        model = Transaction
        fields = [
            "date",
            "operation_time",
            "description",
            "amount",
            "account",
            "external_id",
        ]
        labels = {
            "operation_time": "Orario (facoltativo)",
            "description": "Descrizione (facoltativa)",
            "account": "Conto o carta",
            "external_id": "Identificativo esterno (facoltativo)",
        }
        widgets = {
            "operation_time": forms.TimeInput(attrs={"type": "time"}),
            "description": forms.TextInput(
                attrs={"placeholder": "Es. spesa al supermercato"}
            ),
            "external_id": forms.TextInput(
                attrs={"placeholder": "Codice univoco della banca, se presente"}
            ),
        }

    def __init__(self, *args, flow="", **kwargs):
        super().__init__(*args, **kwargs)
        self.flow = flow
        self.fields["description"].required = False
        self.fields["account"].queryset = Account.objects.filter(active=True)
        self.fields["subcategory"] = forms.ModelChoiceField(
            queryset=Subcategory.objects.none(), label="Sottocategoria"
        )
        self.fields["subcategory"].required = True
        if self.instance and self.instance.pk:
            self.fields["account"].queryset = self.fields[
                "account"
            ].queryset | Account.objects.filter(pk=self.instance.account_id)
            category = self.instance.subcategory.category
            self.initial["category"] = category.pk
            self.initial["subcategory"] = self.instance.subcategory_id
            if self.instance.kind in FLEXIBLE_EXPENSE_KINDS:
                self.initial["expense_kind"] = self.instance.kind
            self.fields["category"].queryset = Category.objects.filter(
                active=True
            ) | Category.objects.filter(pk=category.pk)
            qs = Subcategory.objects.filter(
                category=category, active=True
            ) | Subcategory.objects.filter(pk=self.instance.subcategory_id)
            self.fields["subcategory"].queryset = qs
        if self.is_bound and str(self.data.get("category", "")).isdigit():
            qs = Subcategory.objects.filter(
                category_id=self.data["category"], active=True
            )
            if self.instance.pk:
                qs = qs | Subcategory.objects.filter(
                    pk=self.instance.subcategory_id, category_id=self.data["category"]
                )
            self.fields["subcategory"].queryset = qs
        if not self.instance.pk and flow in {"entrata", "uscita"}:
            subs = Subcategory.objects.filter(active=True, category__active=True)
            subs = (
                subs.filter(kind="Entrata")
                if flow == "entrata"
                else subs.exclude(kind="Entrata")
            )
            self.fields["category"].queryset = Category.objects.filter(
                pk__in=subs.values("category_id")
            )
            self.fields["subcategory"].queryset = self.fields[
                "subcategory"
            ].queryset.filter(pk__in=subs.values("pk"))
        self.fields["amount"].localize = True
        self.fields["amount"].widget = forms.TextInput(
            attrs={"inputmode": "decimal", "placeholder": "0,00"}
        )
        self.fields["date"].widget = forms.DateInput(
            format="%d/%m/%Y",
            attrs={"placeholder": "gg/mm/aaaa", "inputmode": "numeric"},
        )

    def clean(self):
        cleaned = super().clean()
        category, sub = cleaned.get("category"), cleaned.get("subcategory")
        if category and sub and sub.category_id != category.id:
            self.add_error(
                "subcategory", "La sottocategoria non appartiene alla categoria scelta."
            )
        if sub:
            chosen = cleaned.get("expense_kind")
            if chosen and sub.kind not in FLEXIBLE_EXPENSE_KINDS:
                self.add_error(
                    "expense_kind",
                    "Necessaria ed Extra sono disponibili solo per le spese.",
                )
            if (
                "expense_kind" not in self.data
                and self.instance.pk
                and self.instance.subcategory_id == sub.pk
            ):
                chosen = (
                    self.instance.kind
                    if self.instance.kind in FLEXIBLE_EXPENSE_KINDS
                    else None
                )
            self.instance.subcategory = sub
            self.instance.kind = (
                chosen if chosen and sub.kind in FLEXIBLE_EXPENSE_KINDS else sub.kind
            )
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.subcategory = self.cleaned_data["subcategory"]
        if not obj.order_index:
            from .services import next_order_index

            obj.order_index = next_order_index()
        if commit:
            obj.save()
        return obj


class TransferForm(forms.ModelForm):
    date = forms.DateField(
        label="Data",
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    amount = ItalianMoneyField(
        label="Importo (€)",
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )

    class Meta:
        model = Transfer
        fields = [
            "date",
            "operation_time",
            "source",
            "destination",
            "amount",
            "description",
        ]
        labels = {
            "operation_time": "Orario (facoltativo)",
            "source": "Da conto",
            "destination": "A conto",
            "description": "Descrizione",
        }
        widgets = {"operation_time": forms.TimeInput(attrs={"type": "time"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        accounts = Account.objects.filter(active=True)
        if self.instance and self.instance.pk:
            accounts = accounts | Account.objects.filter(
                pk__in=[self.instance.source_id, self.instance.destination_id]
            )
        self.fields["source"].queryset = accounts
        self.fields["destination"].queryset = accounts
        self.fields["description"].required = False
        self.fields["amount"].localize = True
        self.fields["amount"].widget = forms.TextInput(
            attrs={"inputmode": "decimal", "placeholder": "0,00"}
        )
        self.fields["date"].widget = forms.DateInput(
            format="%d/%m/%Y",
            attrs={"placeholder": "gg/mm/aaaa", "inputmode": "numeric"},
        )

    def clean_description(self):
        return self.cleaned_data.get("description") or "Giroconto"

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not obj.order_index:
            from .services import next_order_index

            obj.order_index = next_order_index()
        if commit:
            obj.save()
        return obj


class UploadForm(forms.Form):
    file = forms.FileField(
        label="File movimenti", help_text="CSV o Excel .xlsx · massimo 10 MB"
    )

    def clean_file(self):
        file = self.cleaned_data["file"]
        if file.size > 10 * 1024 * 1024:
            raise ValidationError("Il file supera il limite di 10 MB.")
        if not file.name.lower().endswith((".csv", ".xlsx")):
            raise ValidationError("Scegli un file CSV o Excel .xlsx.")
        return file


class TaxonomyImportForm(forms.Form):
    file = forms.FileField(
        label="File categorie CSV", help_text="CSV UTF-8 · massimo 1 MB"
    )

    def clean_file(self):
        file = self.cleaned_data["file"]
        if file.size > 1024 * 1024:
            raise ValidationError("Il file supera il limite di 1 MB.")
        if not file.name.lower().endswith(".csv"):
            raise ValidationError("Scegli un file CSV.")
        return file


class RestoreForm(forms.Form):
    file = forms.FileField(label="Backup dati Wallet (.json)")

    def clean_file(self):
        f = self.cleaned_data["file"]
        if f.size > 100 * 1024 * 1024:
            raise ValidationError("Il backup supera il limite di 100 MB.")
        if not f.name.lower().endswith(".json"):
            raise ValidationError("Scegli un backup Wallet in formato .json.")
        return f


class AccountForm(forms.ModelForm):
    initial_balance = ItalianMoneyField(
        label="Saldo iniziale (€)", max_digits=14, decimal_places=2
    )

    class Meta:
        model = Account
        fields = ["name", "account_type", "initial_balance", "active"]
        labels = {"active": "Conto attivo"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["initial_balance"].localize = True
        self.fields["initial_balance"].widget = forms.TextInput(
            attrs={"inputmode": "decimal"}
        )


class CategoryForm(forms.ModelForm):
    color = forms.RegexField(
        r"^#[0-9a-fA-F]{6}$",
        label="Colore",
        widget=forms.TextInput(attrs={"type": "color"}),
    )

    class Meta:
        model = Category
        fields = ["name", "color", "active"]
        labels = {"active": "Categoria attiva"}


class SubcategoryForm(forms.ModelForm):
    class Meta:
        model = Subcategory
        fields = ["category", "name", "kind", "icon", "active"]
        labels = {"category": "Categoria", "active": "Sottocategoria attiva"}

    def clean(self):
        data = super().clean()
        if self.instance.pk and (
            self.instance.transactions.exists()
            or self.instance.monthly_budgets.exists()
        ):
            original = Subcategory.objects.get(pk=self.instance.pk)
            if (
                data.get("kind") != original.kind
                or data.get("category") != original.category
            ):
                raise ValidationError(
                    "Questa sottocategoria ha movimenti o budget: per cambiare tipo o categoria crea una nuova voce e archivia questa. Lo storico viene conservato."
                )
        return data
