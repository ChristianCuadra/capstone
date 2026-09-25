from django.contrib import admin

from .models import RegistroIA


@admin.register(RegistroIA)
class RegistroIAAdmin(admin.ModelAdmin):
    """Solo lectura: es el registro de auditoría y costo de la IA."""

    list_display = ["creado_en", "tipo", "modelo", "usuario", "prospecto", "tokens_entrada", "tokens_salida", "duracion_ms", "exitoso"]
    list_filter = ["tipo", "exitoso", "modelo"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
