"""Decoradores de control de acceso por rol (Alcance 4.3, RNF-01)."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect
from django.urls import reverse

MENSAJE_ACCESO_DENEGADO = "No tienes acceso a esa sección del panel de la agencia."


def _denegar_acceso(request):
    """Usuario con sesión iniciada pero sin el rol requerido (CP-019).

    Se le informa con un mensaje, el intento queda en el registro de auditoría y se le
    envía a su propia vista. No se revela qué había en la sección pedida.
    """
    from apps.core.models import RegistroAuditoria

    RegistroAuditoria.registrar(
        usuario=request.user,
        accion=RegistroAuditoria.Accion.ACCESO_DENEGADO,
        entidad="panel de la agencia",
        detalle=f"{request.method} {request.path}"[:255],
    )
    messages.error(request, MENSAJE_ACCESO_DENEGADO)
    return redirect(_redirigir_segun_rol(request))


def _redirigir_segun_rol(request):
    """A donde mandar a alguien que está logueado pero no tiene el rol requerido."""
    if request.user.is_authenticated:
        if request.user.es_equipo_agencia:
            return reverse("crm:dashboard")
        if request.user.es_cliente:
            return reverse("content:calendario")
    return reverse("account_login")


def requiere_rol_cliente(view_func):
    """Solo Cliente aprobador / Cliente lector. Los demás son redirigidos a su propia vista."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.es_cliente:
            from django.shortcuts import redirect

            return redirect(_redirigir_segun_rol(request))
        return view_func(request, *args, **kwargs)

    return login_required(_wrapped)


def requiere_rol_agencia(view_func):
    """Solo Administradora / Colaboradora. Los demás son redirigidos a su propia vista."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.es_equipo_agencia:
            from django.shortcuts import redirect

            return redirect(_redirigir_segun_rol(request))
        return view_func(request, *args, **kwargs)

    return login_required(_wrapped)


def requiere_equipo(view_func):
    """Panel interno: Administradora, Colaboradora, superusuario o personal sin rol (ver apps.core.access.es_equipo).

    Sin sesión se pide iniciar sesión. Con sesión pero sin acceso (p. ej. un usuario cliente), el intento
    se deniega con mensaje y queda en el registro de auditoría (CP-019).
    """
    from apps.core.access import es_equipo

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not es_equipo(request.user):
            return _denegar_acceso(request)
        return view_func(request, *args, **kwargs)

    return _wrapped


def requiere_administradora(view_func):
    """Solo Administradora (p. ej. gestión de usuarios, catálogo). Ver Alcance 9.3.

    Un intento sin el rol queda en el registro de auditoría y se informa con un mensaje (CP-019).
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if request.user.rol != "administradora" and not request.user.is_superuser:
            return _denegar_acceso(request)
        return view_func(request, *args, **kwargs)

    return login_required(_wrapped)
