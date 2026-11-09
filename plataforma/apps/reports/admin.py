from django.contrib import admin

from .models import ReporteMensual


@admin.register(ReporteMensual)
class ReporteMensualAdmin(admin.ModelAdmin):
    list_display = ("mes", "cliente", "estado", "generado_con_ia", "aprobado_por", "fecha_aprobacion")
    list_filter = ("estado", "generado_con_ia")
