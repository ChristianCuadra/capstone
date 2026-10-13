"""Settings de producción (Vercel). config/wsgi.py los usa automáticamente cuando corre en Vercel.

Variables de entorno obligatorias en el proyecto de Vercel: SECRET_KEY y DATABASE_URL (Supabase, pooler 6543).
Para archivos subidos: AWS_*; para la IA: AI_API_KEY. Ver README, sección «Despliegue en Vercel».
"""

from decouple import Csv, config

from .base import *  # noqa: F403
from .base import DATABASES, STORAGES

DEBUG = False

# *.vercel.app cubre la URL del proyecto y las de cada despliegue; el dominio propio se agrega por variable.
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default=".vercel.app", cast=Csv())
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="https://*.vercel.app", cast=Csv())

# Vercel termina el HTTPS y reenvía la petición: Django debe confiar en ese encabezado para saber que es segura.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
# Vercel ya redirige todo a HTTPS y envía HSTS en sus dominios: hacerlo también en Django sería redundante.
SILENCED_SYSTEM_CHECKS = ["security.W004", "security.W008"]

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
