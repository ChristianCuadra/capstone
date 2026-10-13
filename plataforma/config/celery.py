import os

from celery import Celery

# config/__init__.py importa este módulo antes que wsgi.py: debe elegir los mismos settings que él.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod" if os.environ.get("VERCEL") else "config.settings.dev")

app = Celery("cosmopolitan")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
