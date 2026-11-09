from django.contrib import admin

from .models import CorreoSaliente, Notificacion


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ("creado_en", "usuario", "titulo", "leida")
    list_filter = ("leida",)
    search_fields = ("titulo", "usuario__email")


@admin.register(CorreoSaliente)
class CorreoSalienteAdmin(admin.ModelAdmin):
    list_display = ("creado_en", "destinatario", "asunto", "estado", "intentos", "ultimo_error")
    list_filter = ("estado",)
    search_fields = ("destinatario", "asunto")
    readonly_fields = [f.name for f in CorreoSaliente._meta.fields]
