"""Envío de notificaciones (PC-SOL-02).

Cada aviso se guarda en la plataforma (siempre) y, si el usuario tiene correo, se envía también por correo.
Si el correo falla (servidor caído, credenciales malas, sin internet) queda pendiente y se reintenta:
- en el siguiente aviso que genere la plataforma (se aprovecha la misma petición), y
- con el comando `python manage.py reintentar_correos` (para un cron).
Tras MAX_INTENTOS fallidos queda como «Fallido» y se ve en el admin.

Quién recibe qué lo deciden las funciones de destinatarios de abajo: cada usuario solo recibe avisos
de los clientes que puede ver (misma regla de aislamiento que el resto de la plataforma).
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Rol

from .models import CorreoSaliente, Notificacion

logger = logging.getLogger(__name__)

MAX_INTENTOS = 5
# Espera antes de cada reintento: 5 min, 15 min, 1 h, 3 h.
ESPERAS = [timedelta(minutes=5), timedelta(minutes=15), timedelta(hours=1), timedelta(hours=3)]
REINTENTOS_POR_PETICION = 10


def _intentar(correo):
    correo.intentos += 1
    try:
        send_mail(correo.asunto, correo.cuerpo, settings.DEFAULT_FROM_EMAIL, [correo.destinatario], fail_silently=False)
    except Exception as e:  # cualquier fallo del proveedor deja el correo pendiente
        correo.ultimo_error = f"{type(e).__name__}: {e}"[:300]
        if correo.intentos >= MAX_INTENTOS:
            correo.estado = CorreoSaliente.Estado.FALLIDO
            correo.proximo_intento = None
        else:
            correo.proximo_intento = timezone.now() + ESPERAS[min(correo.intentos - 1, len(ESPERAS) - 1)]
        logger.warning("No se pudo enviar el correo %s (intento %s): %s", correo.pk, correo.intentos, correo.ultimo_error)
    else:
        correo.estado = CorreoSaliente.Estado.ENVIADO
        correo.enviado_en = timezone.now()
        correo.proximo_intento = None
        correo.ultimo_error = ""
    correo.save()
    return correo.estado == CorreoSaliente.Estado.ENVIADO


def reintentar_pendientes(limite=None):
    """Reintenta los correos pendientes cuyo plazo ya venció. Devuelve (enviados, revisados)."""
    pendientes = CorreoSaliente.objects.filter(
        estado=CorreoSaliente.Estado.PENDIENTE, intentos__gt=0, proximo_intento__lte=timezone.now()
    ).order_by("proximo_intento")
    if limite:
        pendientes = pendientes[:limite]
    revisados = enviados = 0
    for correo in pendientes:
        revisados += 1
        enviados += _intentar(correo)
    return enviados, revisados


def notificar(usuarios, titulo, mensaje="", url="", request=None, asunto=None, cuerpo_correo=None):
    """Crea la notificación para cada usuario activo y le envía el correo. Devuelve cuántos se avisaron."""
    url_absoluta = request.build_absolute_uri(url) if (request and url) else url
    avisados = 0
    vistos = set()
    for usuario in usuarios:
        if usuario is None or not usuario.is_active or usuario.pk in vistos:
            continue
        vistos.add(usuario.pk)
        Notificacion.objects.create(usuario=usuario, titulo=titulo[:200], mensaje=mensaje[:500], url=url)
        avisados += 1
        if usuario.email:
            cuerpo = cuerpo_correo or mensaje
            if url_absoluta:
                cuerpo = f"{cuerpo}\n\nRevísalo aquí: {url_absoluta}"
            correo = CorreoSaliente.objects.create(
                destinatario=usuario.email,
                asunto=(asunto or titulo)[:200],
                cuerpo=f"Hola,\n\n{cuerpo}\n\nSaludos,\nAgencia Cosmopolitan",
            )
            _intentar(correo)
    # Se aprovecha la petición para reintentar los que habían fallado antes.
    try:
        reintentar_pendientes(limite=REINTENTOS_POR_PETICION)
    except Exception:  # un reintento nunca debe romper la acción del usuario
        logger.exception("Fallo al reintentar correos pendientes")
    return avisados


# ── Destinatarios ───────────────────────────────────────────────────────────

def equipo_del_cliente(cliente):
    """Administradoras (y superusuarios) más las colaboradoras que tienen asignado ese cliente."""
    User = get_user_model()
    return User.objects.filter(is_active=True).filter(
        Q(rol=Rol.ADMINISTRADORA) | Q(is_superuser=True) | Q(rol=Rol.COLABORADORA, clientes_asignados=cliente)
    ).distinct()


def usuarios_del_cliente(cliente, solo_aprobadores=False):
    roles = [Rol.CLIENTE_APROBADOR] if solo_aprobadores else [Rol.CLIENTE_APROBADOR, Rol.CLIENTE_LECTOR]
    return cliente.usuarios.filter(is_active=True, rol__in=roles)
