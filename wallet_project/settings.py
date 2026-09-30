from pathlib import Path
import os
import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
WALLET_ENV = os.environ.get("WALLET_ENV", "local").strip().lower()
IS_PRODUCTION = WALLET_ENV == "production"
SECRET_KEY = os.environ.get(
    "WALLET_SECRET_KEY", "wallet-locale-chiave-solo-per-sviluppo-locale"
)
if IS_PRODUCTION and (
    not os.environ.get("WALLET_SECRET_KEY") or SECRET_KEY.startswith("wallet-locale")
):
    raise ImproperlyConfigured(
        "Imposta WALLET_SECRET_KEY come variabile segreta prima di avviare il Wallet in produzione."
    )
WALLET_OWNER_USERNAME = os.environ.get("WALLET_OWNER_USERNAME", "").strip()
if IS_PRODUCTION and not WALLET_OWNER_USERNAME:
    raise ImproperlyConfigured(
        "Imposta WALLET_OWNER_USERNAME con l'account proprietario del wallet."
    )
DEBUG = False if IS_PRODUCTION else os.environ.get("WALLET_DEBUG", "1") == "1"
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("WALLET_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if h.strip()
]
if IS_PRODUCTION and not os.environ.get("WALLET_ALLOWED_HOSTS"):
    raise ImproperlyConfigured(
        "Imposta WALLET_ALLOWED_HOSTS con il dominio Northflank del servizio."
    )
CSRF_TRUSTED_ORIGINS = [
    u.strip()
    for u in os.environ.get("WALLET_CSRF_TRUSTED_ORIGINS", "").split(",")
    if u.strip()
]

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URI")
if IS_PRODUCTION and not DATABASE_URL:
    raise ImproperlyConfigured(
        "Configura DATABASE_URL (o POSTGRES_URI) per collegare PostgreSQL in produzione."
    )
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=int(os.environ.get("WALLET_DB_CONN_MAX_AGE", "60")),
            conn_health_checks=True,
        )
    }
    if (
        IS_PRODUCTION
        and DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql"
    ):
        raise ImproperlyConfigured(
            "In produzione DATABASE_URL (o POSTGRES_URI) deve puntare a PostgreSQL."
        )
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(os.environ.get("WALLET_DB_PATH", BASE_DIR / "wallet.sqlite3")),
            "OPTIONS": {"timeout": 20},
        }
    }

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "django.contrib.sessions",
    "django.contrib.messages",
    "wallet.apps.WalletConfig",
]
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "wallet.middleware.SingleOwnerMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
if IS_PRODUCTION:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
ROOT_URLCONF = "wallet_project.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "wallet_project.wsgi.application"
LANGUAGE_CODE = "it-it"
TIME_ZONE = "Europe/Rome"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = []
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_BACKEND = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
    if (IS_PRODUCTION or os.environ.get("WALLET_BUILD_STATIC") == "1")
    else "django.contrib.staticfiles.storage.StaticFilesStorage"
)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": STATICFILES_BACKEND},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_ENGINE = "django.contrib.sessions.backends.db"
MESSAGE_STORAGE = "django.contrib.messages.storage.fallback.FallbackStorage"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 105 * 1024 * 1024
# La revisione invia più campi per ogni movimento; 100.000 copre l'import
# massimo di 10.000 righe senza rimuovere il limite anti-abuso di Django.
DATA_UPLOAD_MAX_NUMBER_FIELDS = 100_000
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = IS_PRODUCTION
CSRF_COOKIE_SECURE = IS_PRODUCTION
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = IS_PRODUCTION
SECURE_REDIRECT_EXEMPT = [r"^healthz/?$"]
SECURE_HSTS_SECONDS = int(
    os.environ.get("WALLET_HSTS_SECONDS", "3600" if IS_PRODUCTION else "0")
)
X_FRAME_OPTIONS = "DENY"
