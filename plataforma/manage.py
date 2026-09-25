#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    # `manage.py test` nunca debe crear bases en Supabase: usa SQLite (config/settings/test.py).
    settings_por_defecto = 'config.settings.test' if sys.argv[1:2] == ['test'] else 'config.settings.dev'
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', settings_por_defecto)
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
