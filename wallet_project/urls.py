from django.urls import path
from django.urls import reverse_lazy
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from wallet import views
from wallet.forms import WalletAuthenticationForm, WalletPasswordChangeForm

urlpatterns = [
    path(
        "accedi/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            authentication_form=WalletAuthenticationForm,
        ),
        name="login",
    ),
    path("esci/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "password/cambia/",
        auth_views.PasswordChangeView.as_view(
            form_class=WalletPasswordChangeForm,
            template_name="registration/password_change_form.html",
            success_url=reverse_lazy("password_change_done"),
        ),
        name="password_change",
    ),
    path(
        "password/cambiata/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="registration/password_change_done.html"
        ),
        name="password_change_done",
    ),
    path("healthz/", views.healthz, name="healthz"),
    path(
        "",
        RedirectView.as_view(
            pattern_name="dashboard", query_string=True, permanent=False
        ),
        name="home",
    ),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("overview/", views.overview, name="overview"),
    path(
        "overview/categorie-dati/",
        views.overview_expense_data,
        name="overview_expense_data",
    ),
    path(
        "dashboard/categorie-dati/",
        RedirectView.as_view(
            pattern_name="overview_expense_data", query_string=True, permanent=False
        ),
        name="dashboard_expense_data",
    ),
    path("budget/", views.budget, name="budget"),
    path("movimenti/", views.transactions, name="transactions"),
    path("movimenti/nuovo/", views.transaction_form, name="transaction_new"),
    path(
        "movimenti/<uuid:uid>/modifica/",
        views.transaction_form,
        name="transaction_edit",
    ),
    path(
        "movimenti/<uuid:uid>/elimina/",
        views.transaction_delete,
        name="transaction_delete",
    ),
    path("importa/", views.import_view, name="import"),
    path("importa/conferma/", views.import_confirm, name="import_confirm"),
    path("giroconti/", views.transfers, name="transfers"),
    path("giroconti/<uuid:uid>/modifica/", views.transfer_edit, name="transfer_edit"),
    path(
        "giroconti/<uuid:uid>/elimina/", views.transfer_delete, name="transfer_delete"
    ),
    path("configurazione/", views.settings_page, name="settings"),
    path("categorie/", views.categories_page, name="categories"),
    path("esporta/", views.export_csv, name="export_csv"),
    path("backup/", views.backup, name="backup"),
    path("backup/ripristina/", views.restore_backup, name="restore_backup"),
]
