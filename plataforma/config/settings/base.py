"""
Settings base de Plataforma Cosmopolitan.

Todas las variables sensibles se leen desde .env mediante python-decouple.
"""

import ssl
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent.parent


# --- Core -------------------------------------------------------------------

SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.clients",
    "apps.crm",
    "apps.content",
    "apps.metrics",
    "apps.reports",
    "apps.ai",
    "apps.notifications",
    "apps.website",
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    # Terceros
    "allauth",
    "allauth.account",
    "django_htmx",
    "storages",
    *LOCAL_APPS,
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    # Debe ir después de Session y Authentication: necesita request.user y request.session.
    "apps.core.middleware.TenantMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.website.context_processors.agencia",
            ],
        },
    },
]


# --- Base de datos (Supabase PostgreSQL + pgvector) --------------------------
# La extensión pgvector se habilita en la migración apps/core/migrations/0001_enable_pgvector.py.


def parse_database_url(url):
    """Convierte postgres://user:pass@host:port/db?sslmode=require en un dict de DATABASES."""
    parsed = urlparse(url)
    if parsed.scheme not in ("postgres", "postgresql"):
        raise ValueError(f"Esquema de DATABASE_URL no soportado: {parsed.scheme!r}")
    db = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
        "OPTIONS": dict(parse_qsl(parsed.query)),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
    # El pooler de Supabase en modo transacción (puerto 6543) no soporta cursores del lado del servidor.
    if db["PORT"] == "6543":
        db["DISABLE_SERVER_SIDE_CURSORS"] = True
    return db


DATABASE_URL = config("DATABASE_URL", default="")
DATABASES = {"default": parse_database_url(DATABASE_URL)} if DATABASE_URL else {}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Autenticación (django-allauth) ------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_USER_MODEL_USERNAME_FIELD = "username"
# Sin registro público y con redirección según rol (equipo → panel, cliente → portal).
ACCOUNT_ADAPTER = "apps.accounts.adapter.CuentaAdapter"
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "/"


# --- Internacionalización ----------------------------------------------------

LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True


# --- Archivos estáticos y media ----------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Supabase Storage expone una API compatible con S3.
# AWS_S3_ENDPOINT_URL = https://<project-ref>.supabase.co/storage/v1/s3
AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default="")
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="")
AWS_S3_ENDPOINT_URL = config("AWS_S3_ENDPOINT_URL", default="")
AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="us-east-1")

# Django 5.1 eliminó DEFAULT_FILE_STORAGE / STATICFILES_STORAGE; su reemplazo es STORAGES.
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": AWS_ACCESS_KEY_ID,
            "secret_key": AWS_SECRET_ACCESS_KEY,
            "bucket_name": AWS_STORAGE_BUCKET_NAME,
            "endpoint_url": AWS_S3_ENDPOINT_URL,
            "region_name": AWS_S3_REGION_NAME,
            "addressing_style": "path",  # Supabase requiere path-style
            "signature_version": "s3v4",
            "default_acl": None,
            "file_overwrite": False,
            "querystring_auth": True,  # URLs firmadas: el bucket puede ser privado
        },
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# --- Celery (Upstash Redis) --------------------------------------------------

REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# Upstash solo acepta conexiones TLS (rediss://).
if REDIS_URL.startswith("rediss://"):
    CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
    CELERY_REDIS_BACKEND_USE_SSL = {"ssl_cert_reqs": ssl.CERT_REQUIRED}


# --- Servicios externos ------------------------------------------------------

# Proveedor de IA: Google Gemini (API REST). Sin AI_API_KEY, las funciones de IA quedan desactivadas.
AI_API_KEY = config("AI_API_KEY", default="")
AI_MODEL = config("AI_MODEL", default="") or "gemini-2.5-flash"
EMAIL_API_KEY = config("EMAIL_API_KEY", default="")
