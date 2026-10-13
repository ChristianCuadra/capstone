"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Vercel define VERCEL=1 en sus funciones: ahí se usan los settings de producción.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.prod' if os.environ.get('VERCEL') else 'config.settings.dev')

application = get_wsgi_application()

# El runtime de Python de Vercel busca la aplicación WSGI con el nombre `app`.
app = application
