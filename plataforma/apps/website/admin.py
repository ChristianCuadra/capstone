from django.contrib import admin

from apps.core.admin_mixins import AuditoriaAdminMixin

from .models import Contenido


@admin.register(Contenido)
class ContenidoAdmin(AuditoriaAdminMixin, admin.ModelAdmin):
    list_display = ("titulo", "seccion", "estado", "publicado_en", "actualizado_en")
    list_filter = ("seccion", "estado")
    search_fields = ("titulo", "resumen", "cuerpo")
    prepopulated_fields = {"slug": ("titulo",)}
    auditoria_entidad = "contenido del sitio"
