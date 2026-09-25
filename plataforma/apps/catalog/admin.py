from django.contrib import admin

from .models import Plan, PlanEntregable, Servicio, TipoEntregable


class PlanEntregableInline(admin.TabularInline):
    model = PlanEntregable
    extra = 1
    autocomplete_fields = ["tipo_entregable"]


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ["nombre", "precio_mensual", "precio_primer_mes", "destacado", "visible_en_sitio", "activo", "orden"]
    list_editable = ["visible_en_sitio", "activo", "orden"]
    list_filter = ["activo", "visible_en_sitio"]
    search_fields = ["nombre"]
    prepopulated_fields = {"slug": ["nombre"]}
    inlines = [PlanEntregableInline]


@admin.register(TipoEntregable)
class TipoEntregableAdmin(admin.ModelAdmin):
    list_display = ["nombre", "nombre_plural", "tiene_cuota", "activo", "orden"]
    list_editable = ["orden"]
    list_filter = ["tiene_cuota", "activo"]
    search_fields = ["nombre"]
    prepopulated_fields = {"slug": ["nombre"]}


@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    list_display = ["nombre", "precio", "modalidad_cobro", "visible_en_sitio", "activo", "orden"]
    list_editable = ["visible_en_sitio", "activo", "orden"]
    list_filter = ["modalidad_cobro", "activo", "visible_en_sitio"]
    search_fields = ["nombre"]
    prepopulated_fields = {"slug": ["nombre"]}
