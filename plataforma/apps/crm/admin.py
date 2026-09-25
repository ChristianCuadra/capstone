from django.contrib import admin

from .models import Cotizacion, CotizacionItem, Interaccion, Prospecto, Tarea


class InteraccionInline(admin.TabularInline):
    model = Interaccion
    extra = 0
    fields = ["fecha", "tipo", "titulo", "autor"]


@admin.register(Prospecto)
class ProspectoAdmin(admin.ModelAdmin):
    list_display = ["empresa", "nombre", "correo", "etapa", "plan_sugerido", "presupuesto", "creado_en"]
    list_filter = ["etapa", "presupuesto", "rubro", "como_nos_conocio"]
    search_fields = ["empresa", "nombre", "correo"]
    readonly_fields = ["creado_en", "actualizado_en", "diagnostico_generado_en", "diagnostico_revisado_en"]
    inlines = [InteraccionInline]

    def save_model(self, request, obj, form, change):
        # Los prospectos ingresados a mano desde el panel se marcan con su canal.
        if not change and obj.canal == Prospecto.Canal.FORMULARIO_SITIO:
            obj.canal = Prospecto.Canal.MANUAL
        super().save_model(request, obj, form, change)


class CotizacionItemInline(admin.TabularInline):
    model = CotizacionItem
    extra = 0


@admin.register(Cotizacion)
class CotizacionAdmin(admin.ModelAdmin):
    list_display = ["numero", "prospecto", "estado", "creado_en", "enviada_en"]
    list_filter = ["estado"]
    search_fields = ["numero", "prospecto__empresa"]
    readonly_fields = ["numero", "creado_en", "actualizado_en"]
    inlines = [CotizacionItemInline]


@admin.register(Tarea)
class TareaAdmin(admin.ModelAdmin):
    list_display = ["titulo", "fecha", "responsable", "prospecto", "completada"]
    list_filter = ["completada", "responsable"]
    search_fields = ["titulo"]
