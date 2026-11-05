"""Filtros para las páginas de cuenta (login, 2FA, recuperar contraseña)."""

from django import template
from django.conf import settings

register = template.Library()


@register.filter
def es_del_equipo(user):
    """Misma regla que el panel (apps.core.access.es_equipo): administradora, colaboradora o personal sin rol."""
    from apps.core.access import es_equipo

    return es_equipo(user)


@register.filter
def entra_al_panel(user):
    """True si el usuario puede abrir el panel ahora mismo.

    Al equipo sin 2FA el panel lo devuelve a configurarlo (Exigir2FAEquipoMiddleware): mostrarle «Ir al panel»
    mientras activa el 2FA lo dejaría dando vueltas en la misma pantalla.
    """
    from allauth.mfa.utils import is_mfa_enabled

    from apps.core.access import es_equipo

    if not es_equipo(user):
        return False
    return not getattr(settings, "EXIGIR_2FA_EQUIPO", False) or is_mfa_enabled(user)
