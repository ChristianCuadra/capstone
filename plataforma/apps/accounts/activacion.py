"""Activación de cuentas de clientes (PC-AUT-07).

Registro cerrado (CuentaAdapter.is_open_for_signup = False): la administradora crea la cuenta del
cliente desde su ficha y la persona la activa definiendo su propia contraseña desde un enlace que
le llega por correo. La agencia nunca conoce ni escribe la contraseña del cliente.

- Una cuenta invitada queda con contraseña inutilizable: no puede iniciar sesión hasta activarla.
- El enlace es de un solo uso (deja de servir en cuanto se define la contraseña) y vence según
  PASSWORD_RESET_TIMEOUT (3 días por defecto en Django).
- Si el correo no se puede enviar (p. ej. sin proveedor configurado), la cuenta igual queda creada y
  la administradora puede copiar el enlace desde la ficha para enviarlo por otro canal.
"""

import logging

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)


class ActivacionTokenGenerator(PasswordResetTokenGenerator):
    """Igual que el de recuperar contraseña, pero con su propia sal: un token no sirve para el otro flujo."""

    key_salt = "apps.accounts.activacion.ActivacionTokenGenerator"


token_activacion = ActivacionTokenGenerator()


class Estado:
    PENDIENTE = "pendiente"
    ACTIVA = "activa"
    DESACTIVADA = "desactivada"


ETIQUETAS_ESTADO = {
    Estado.PENDIENTE: "Pendiente de activación",
    Estado.ACTIVA: "Activa",
    Estado.DESACTIVADA: "Desactivada",
}


def estado_cuenta(usuario):
    """Pendiente = invitada y nunca activada (sin contraseña propia ni inicio de sesión)."""
    if not usuario.is_active:
        return Estado.DESACTIVADA
    if not usuario.has_usable_password() and usuario.last_login is None:
        return Estado.PENDIENTE
    return Estado.ACTIVA


def dias_vigencia():
    return max(1, settings.PASSWORD_RESET_TIMEOUT // 86400)


def enlace_activacion(request, usuario):
    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    ruta = reverse("cuenta_activar", args=[uid, token_activacion.make_token(usuario)])
    return request.build_absolute_uri(ruta)


def username_unico(email):
    """Nombre de usuario a partir del correo (parte antes de la @), sin chocar con uno existente."""
    from .models import User

    base = (email.split("@")[0] or "cliente")[:140]
    candidato, n = base, 2
    while User.objects.filter(username__iexact=candidato).exists():
        candidato, n = f"{base}{n}", n + 1
    return candidato


def enviar_invitacion(request, usuario):
    """Envía el correo de activación. Devuelve True si salió; si falla, lo deja en el log y devuelve False."""
    contexto = {
        "usuario": usuario,
        "cliente": usuario.cliente,
        "enlace": enlace_activacion(request, usuario),
        "dias": dias_vigencia(),
    }
    asunto = "Activa tu cuenta en el portal de clientes · Agencia Cosmopolitan"
    try:
        mensaje = EmailMultiAlternatives(
            subject=asunto,
            body=render_to_string("account/email/activacion_cuenta.txt", contexto),
            from_email=None,  # DEFAULT_FROM_EMAIL
            to=[usuario.email],
        )
        mensaje.attach_alternative(render_to_string("account/email/activacion_cuenta.html", contexto), "text/html")
        mensaje.send(fail_silently=False)
        return True
    except Exception:  # noqa: BLE001 — sin proveedor de correo no debe botarse el panel
        logger.exception("No se pudo enviar la invitación de activación a %s", usuario.email)
        return False
