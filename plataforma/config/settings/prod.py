"""Settings de producción (Vercel). config/wsgi.py los usa automáticamente cuando corre en Vercel.

Variables de entorno obligatorias en el proyecto de Vercel: SECRET_KEY y DATABASE_URL (Supabase, pooler 6543).
Para archivos subidos: AWS_*; para la IA: AI_API_KEY. Ver README, sección «Despliegue en Vercel».
"""

import os

from decouple import Csv, config

from .base import *  # noqa: F403
from .base import DATABASES, STORAGES

DEBUG = False

# Solo los dominios de este proyecto: antes se aceptaba cualquier *.vercel.app, incluidos sitios de terceros.
# Vercel entrega sus URLs en variables de sistema (producción, rama y despliegue); el dominio propio se agrega
# con ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS. Si Vercel no entregara ninguna, se vuelve al comodín para no quedar fuera.
_DOMINIOS_VERCEL = sorted({
    d for d in (os.environ.get(v, "") for v in ("VERCEL_PROJECT_PRODUCTION_URL", "VERCEL_BRANCH_URL", "VERCEL_URL")) if d
})
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default=",".join(_DOMINIOS_VERCEL) or ".vercel.app", cast=Csv())
CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default=",".join(f"https://{d}" for d in _DOMINIOS_VERCEL) or "https://*.vercel.app",
    cast=Csv(),
)

# Vercel termina el HTTPS y reenvía la petición: Django debe confiar en ese encabezado para saber que es segura.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
# HSTS: el navegador solo usará HTTPS durante un año, también en el dominio propio (Vercel lo envía solo en los suyos).
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
# Vercel ya redirige todo a HTTPS antes de llegar a Django (W008). HSTS no se extiende a subdominios ni se pide
# la lista de precarga (W005, W021): otros subdominios de la agencia podrían no tener HTTPS.
SILENCED_SYSTEM_CHECKS = ["security.W008", "security.W005", "security.W021"]

# Funciones serverless: cada instancia vive poco, así que no se mantienen conexiones abiertas a Supabase.
if DATABASES:
    DATABASES["default"]["CONN_MAX_AGE"] = 0

# Sin collectstatic en el despliegue: WhiteNoise sirve los estáticos (admin, allauth) directo desde las apps.
WHITENOISE_USE_FINDERS = True
STATIC_ROOT = None  # no hay carpeta staticfiles (no se corre collectstatic); evita un aviso en cada arranque
STORAGES = {**STORAGES, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}

# En Vercel no hay worker de Celery: si se encola una tarea, se ejecuta en el momento (y sus errores se ven).
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Mientras no haya proveedor de correo, los correos quedan en los logs de Vercel en vez de botar la página
# (p. ej. recuperar contraseña). La asesoría gratuita igual queda guardada como prospecto en el panel.
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")

# Errores en los logs de Vercel (Functions → Logs).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
