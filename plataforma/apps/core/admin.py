from django.contrib import admin

from .models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("creado_en", "usuario", "accion", "entidad", "entidad_id", "detalle")
    list_filter = ("accion", "entidad")
    search_fields = ("detalle", "entidad_id", "usuario__username", "usuario__email")
    date_hierarchy = "creado_en"
    ordering = ("-creado_en",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
