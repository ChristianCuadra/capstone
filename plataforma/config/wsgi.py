"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Vercel (VERCEL=1, entrada en api/index.py) y Render (RENDER=true, gunicorn) usan los settings de producción.
EN_LA_NUBE = os.environ.get('VERCEL') or os.environ.get('RENDER')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.prod' if EN_LA_NUBE else 'config.settings.dev')

application = get_wsgi_application()
