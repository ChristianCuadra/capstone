from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class UsuarioAdmin(UserAdmin):
    """Extiende el admin estándar de Django con el rol y el/los cliente(s) asignados (Alcance 4.3)."""

    fieldsets = UserAdmin.fieldsets + (
        ("Rol y cliente (Alcance 4.3)", {"fields": ("rol", "cliente", "clientes_asignados")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Rol y cliente (Alcance 4.3)", {"fields": ("rol", "cliente", "clientes_asignados")}),
    )
    list_display = (*UserAdmin.list_display, "rol", "cliente")
    list_filter = (*UserAdmin.list_filter, "rol")
    filter_horizontal = (*UserAdmin.filter_horizontal, "clientes_asignados")
    autocomplete_fields = ("cliente",)
