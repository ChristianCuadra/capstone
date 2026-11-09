from django.core.management.base import BaseCommand

from apps.notifications.services import reintentar_pendientes


class Command(BaseCommand):
    help = "Reintenta los correos de notificación que fallaron y cuyo plazo de espera ya venció (PC-SOL-02)."

    def handle(self, *args, **options):
        enviados, revisados = reintentar_pendientes()
        self.stdout.write(f"Correos revisados: {revisados}. Enviados: {enviados}.")
