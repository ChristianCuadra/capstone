from django.contrib import admin

from apps.core.access import clientes_visibles

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ["nombre", "rut", "plan", "activo", "creado_en"]
    list_filter = ["activo", "plan"]
    search_fields = ["nombre", "rut", "contacto_correo"]

    def get_queryset(self, request):
        # Mismo criterio que el panel: cada usuario ve solo los clientes que le corresponden.
        return clientes_visibles(request.user)
