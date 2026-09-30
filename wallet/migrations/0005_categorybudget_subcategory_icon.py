from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("wallet", "0004_userpreference_category_selection")]

    operations = [
        migrations.AddField(
            model_name="subcategory",
            name="icon",
            field=models.CharField(blank=True, default="tag", max_length=40, verbose_name="icona"),
        ),
        migrations.CreateModel(
            name="CategoryBudget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("month", models.DateField(help_text="Usare il primo giorno del mese.", verbose_name="mese")),
                ("amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14, verbose_name="budget mensile")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="monthly_budgets", to="wallet.category")),
            ],
            options={"verbose_name": "budget mensile", "verbose_name_plural": "budget mensili", "ordering": ["category__name"]},
        ),
        migrations.AddConstraint(
            model_name="categorybudget",
            constraint=models.UniqueConstraint(fields=("month", "category"), name="unique_budget_category_month"),
        ),
        migrations.AddConstraint(
            model_name="categorybudget",
            constraint=models.CheckConstraint(condition=models.Q(("amount__gte", 0)), name="budget_amount_nonnegative"),
        ),
    ]
