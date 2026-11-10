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
    "django.contrib.sitemaps",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Terceros
    "allauth",
    "allauth.account",
    "allauth.mfa",
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
    # PC-CAP-01: guarda en la sesión el origen de la visita (UTM / sitio de referencia) para el prospecto.
    "apps.website.middleware.OrigenVisitaMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # El equipo de la agencia debe tener 2FA activo para entrar al panel y al admin (ver EXIGIR_2FA_EQUIPO).
    # Va después de MessageMiddleware: avisa con un mensaje por qué se le pide configurarlo.
    "apps.accounts.middleware.Exigir2FAEquipoMiddleware",
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
                "apps.website.context_processors.analitica",
                "apps.website.context_processors.metadatos_pagina",
                "apps.notifications.context_processors.notificaciones",
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

ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = "username"
# Aviso por correo (sin incluir los codigos) cuando se activa/desactiva 2FA
# o se generan nuevos codigos de recuperacion (PC-AUT-02).
ACCOUNT_EMAIL_NOTIFICATIONS = True
# Sin registro público y con redirección según rol (equipo → panel, cliente → portal).
ACCOUNT_ADAPTER = "apps.accounts.adapter.CuentaAdapter"
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "/"

# 2FA (PC-AUT-02, Alcance 4.3): TOTP con app autenticadora + códigos de recuperación.
# Sin webauthn/passkeys por ahora para no depender de esas librerías extra.
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TOTP_ISSUER = "Cosmopolitan"
# Se acepta el código del intervalo de 30 s actual y también el anterior o el siguiente: los relojes de teléfonos y
# servidores nunca están perfectamente sincronizados (con 0, un desfase de pocos segundos rechazaba códigos correctos).
MFA_TOTP_TOLERANCE = 1
# El equipo (administradora y colaboradoras) ve datos personales de todos los clientes y prospectos:
# sin 2FA activo no entra al panel ni al admin, se le pide configurarlo primero (Ley 21.719, medidas de seguridad).
# Solo para una emergencia (p. ej. nadie puede configurar la app) se puede apagar con EXIGIR_2FA_EQUIPO=False.
EXIGIR_2FA_EQUIPO = config("EXIGIR_2FA_EQUIPO", default=True, cast=bool)

# Sesiones: se cierran tras 8 horas sin actividad (cada visita renueva el plazo). Sin «Recordarme»,
# al cerrar el navegador. Antes duraban 2 semanas.
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_SAVE_EVERY_REQUEST = True

# Caché compartida en la base de datos: en Vercel cada instancia tiene su propia memoria, así que los límites
# de intentos de inicio de sesión (allauth) y de los formularios públicos no se cumplían entre instancias.
# La tabla se crea al migrar (apps.core.apps); si aún no existe, se usa la memoria de la instancia como antes.
CACHES = {"default": {"BACKEND": "apps.core.cache.CacheBaseDatosTolerante", "LOCATION": "cache_django"}}

# Analitica con consentimiento (PC-SEO-02, Alcance 4.5): IDs reales via variables de
# entorno (Esteban los confirma con la agencia). Vacio = esa herramienta no se carga.
GA4_MEASUREMENT_ID = config("GA4_MEASUREMENT_ID", default="")
GTM_CONTAINER_ID = config("GTM_CONTAINER_ID", default="")
META_PIXEL_ID = config("META_PIXEL_ID", default="")


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
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
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
# gemini-2.5-flash ya no se habilita para cuentas nuevas de Google AI Studio (oct. 2026).
# Flash-Lite: borradores de igual calidad en ~3 s; gemini-3.8-flash tardaba 18-50 s según la demanda.
AI_MODEL = config("AI_MODEL", default="") or "gemini-3.5-flash-lite"
# Respaldo con otros proveedores gratuitos (API compatible con OpenAI). Si Gemini se queda sin cuota, falla o no
# tiene clave, se intenta con el siguiente de AI_PROVEEDORES que tenga clave. Ver apps/ai/proveedores.py.
AI_PROVEEDORES = [p.strip() for p in config("AI_PROVEEDORES", default="gemini,groq,openrouter").split(",") if p.strip()]
GROQ_API_KEY = config("GROQ_API_KEY", default="")
GROQ_MODEL = config("GROQ_MODEL", default="") or "llama-3.3-70b-versatile"
OPENROUTER_API_KEY = config("OPENROUTER_API_KEY", default="")
OPENROUTER_MODEL = config("OPENROUTER_MODEL", default="") or "openrouter/free"
EMAIL_API_KEY = config("EMAIL_API_KEY", default="")

# Correo saliente: activación de cuentas (PC-AUT-07), recuperar contraseña y envío de cotizaciones.
# Para conectar un proveedor por SMTP (p. ej. Brevo) basta con definir estas variables en el entorno
# y EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend (ver settings/prod.py). En dev y tests
# el correo se muestra en la consola.
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_TIMEOUT = 10  # segundos: si el proveedor no responde, no se cuelga la página
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="Agencia Cosmopolitan <contacto@agenciacosmopolitan.cl>")

WHITENOISE_MANIFEST_STRICT = False