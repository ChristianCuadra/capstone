"""Decoradores de control de acceso por rol (Alcance 4.3, RNF-01)."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.urls import reverse


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


def requiere_administradora(view_func):
    """Solo Administradora (p. ej. gestión de usuarios, catálogo). Ver Alcance 9.3."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if request.user.rol != "administradora" and not request.user.is_superuser:
            from django.shortcuts import redirect

            return redirect(_redirigir_segun_rol(request))
        return view_func(request, *args, **kwargs)

    return login_required(_wrapped)
