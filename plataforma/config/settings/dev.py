from .base import *  # noqa: F403
from .base import BASE_DIR, DATABASE_URL, STORAGES, AWS_STORAGE_BUCKET_NAME

DEBUG = True

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

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
