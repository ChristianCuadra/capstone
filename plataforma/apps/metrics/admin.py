from django.contrib import admin

from .models import ImportacionMetricas, MetricaDiaria


@admin.register(ImportacionMetricas)
class ImportacionMetricasAdmin(admin.ModelAdmin):
    list_display = ("creado_en", "cliente", "fuente", "nombre_archivo", "filas", "desde", "hasta", "subido_por")
    list_filter = ("fuente",)


@admin.register(MetricaDiaria)
class MetricaDiariaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "cliente", "fuente", "alcance", "interacciones", "seguidores", "gasto", "resultados")
    list_filter = ("fuente", "cliente")
