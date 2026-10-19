from django.contrib import admin

from apps.core.admin_mixins import AuditoriaAdminMixin

from .models import ConfiguracionAgencia, Contenido, MetadatosPagina


@admin.register(Contenido)
class ContenidoAdmin(AuditoriaAdminMixin, admin.ModelAdmin):
    list_display = ("titulo", "seccion", "estado", "publicado_en", "actualizado_en")
    list_filter = ("seccion", "estado")
    search_fields = ("titulo", "resumen", "cuerpo")
    prepopulated_fields = {"slug": ("titulo",)}
    auditoria_entidad = "contenido del sitio"


@admin.register(MetadatosPagina)
class MetadatosPaginaAdmin(AuditoriaAdminMixin, admin.ModelAdmin):
    list_display = ("pagina", "meta_titulo", "actualizado_en")
    auditoria_entidad = "SEO de página"


@admin.register(ConfiguracionAgencia)
class ConfiguracionAgenciaAdmin(AuditoriaAdminMixin, admin.ModelAdmin):
    list_display = ("__str__", "correo", "telefono", "actualizado_en")
    auditoria_entidad = "configuración de la agencia"
