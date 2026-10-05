from django.contrib import admin

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ["nombre", "rut", "plan", "activo", "creado_en"]
    list_filter = ["activo", "plan"]
    search_fields = ["nombre", "rut", "contacto_correo"]
