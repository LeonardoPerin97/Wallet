from django.db import migrations, models


def preserve_existing_dashboard_filters(apps, schema_editor):
    UserPreference = apps.get_model("wallet", "UserPreference")
    for preference in UserPreference.objects.all().iterator():
        has_saved_categories = preference.categories.exists()
        preference.all_categories_selected = (
            not preference.no_categories_selected and not has_saved_categories
        )
        # Before Giroconto had its own filter, transfers were included when at
        # least one real category was selected.
        preference.include_transfers = not preference.no_categories_selected
        preference.save(update_fields=["all_categories_selected", "include_transfers"])


class Migration(migrations.Migration):

    dependencies = [
        ("wallet", "0003_userpreference_no_accounts_selected_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="userpreference",
            name="all_categories_selected",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="userpreference",
            name="include_transfers",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(preserve_existing_dashboard_filters, migrations.RunPython.noop),
    ]
