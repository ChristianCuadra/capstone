from .base import *  # noqa: F403
from .base import BASE_DIR, DATABASE_URL, STORAGES, AWS_STORAGE_BUCKET_NAME

DEBUG = True

# Por defecto los correos se imprimen en la terminal. Para enviarlos de verdad (p. ej. Gmail con contraseña de
# aplicación), definir EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend y EMAIL_HOST* en .env.
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")  # noqa: F405

# Sin DATABASE_URL en .env se usa SQLite local, solo para levantar el proyecto.
# pgvector no está disponible en SQLite: la migración que lo habilita se omite.
if not DATABASE_URL:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Sin bucket configurado, los archivos subidos se guardan en MEDIA_ROOT local.
if not AWS_STORAGE_BUCKET_NAME:
    STORAGES = {
        **STORAGES,
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    }
