"""Inicios de sesión en el registro de auditoría (Ley 21.719: poder demostrar quién accedió a los datos y cuándo).

Se registran los exitosos y los fallidos (sin la contraseña: Django la quita de las credenciales antes de
emitir la señal). Sirven para detectar intentos de fuerza bruta y accesos indebidos.
"""

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from apps.core.models import RegistroAuditoria
from apps.core.red import ip_del_cliente


@receiver(user_logged_in, dispatch_uid="auditoria_inicio_sesion")
def registrar_inicio_sesion(sender, request, user, **kwargs):
    RegistroAuditoria.registrar(
        usuario=user,
        accion=RegistroAuditoria.Accion.INICIO_SESION,
        entidad="inicio de sesión",
        entidad_id=user.pk,
        detalle=f"{user.email or user.username} · IP {ip_del_cliente(request)}"[:255],
    )


@receiver(user_login_failed, dispatch_uid="auditoria_inicio_sesion_fallido")
def registrar_inicio_sesion_fallido(sender, credentials, request=None, **kwargs):
    intento = credentials.get("email") or credentials.get("username") or credentials.get("login") or "?"
    RegistroAuditoria.registrar(
        usuario=None,
        accion=RegistroAuditoria.Accion.SESION_FALLIDA,
        entidad="inicio de sesión",
        detalle=f"{str(intento)[:150]} · IP {ip_del_cliente(request)}"[:255],
    )
