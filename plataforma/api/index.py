"""Punto de entrada de Vercel: todas las rutas llegan aquí (ver vercel.json) y se entregan a Django."""

import os
import sys
from pathlib import Path

# La función corre desde api/: la raíz del proyecto (donde están config/ y apps/) debe estar en el path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

from config.wsgi import application  # noqa: E402

# El runtime de Python de Vercel busca la aplicación WSGI con el nombre `app`.
app = application
