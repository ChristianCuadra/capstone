from django.apps import AppConfig
from django.db.models.signals import post_migrate


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'

    def ready(self):
        from .seguridad_bd import asegurar_base

        # Después de cada `migrate` (una vez, con la señal de esta app): tabla de caché y RLS en Supabase.
        post_migrate.connect(asegurar_base, sender=self, dispatch_uid="core_asegurar_base")
