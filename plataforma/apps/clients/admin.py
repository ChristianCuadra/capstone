from django.contrib import admin

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ["nombre", "activo", "creado_en"]
    list_filter = ["activo"]
    search_fields = ["nombre"]
