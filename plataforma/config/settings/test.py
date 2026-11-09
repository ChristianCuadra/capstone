"""Settings de tests: SQLite en memoria y archivos locales, sin tocar Supabase aunque .env tenga credenciales."""

from .dev import *  # noqa: F403
from .dev import STORAGES

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

STORAGES = {
    **STORAGES,
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Caché en memoria (sin tabla) y sin exigir 2FA: los tests del panel inician sesión con force_login.
# Los tests de la exigencia de 2FA la activan con override_settings.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
EXIGIR_2FA_EQUIPO = False

# Los tests nunca llaman a Gemini aunque .env tenga clave: los que prueban la IA la simulan con override_settings.
AI_API_KEY = ""
GROQ_API_KEY = ""
OPENROUTER_API_KEY = ""
