"""Activación de la cuenta del cliente (PC-AUT-07) y entrada al admin de Django por el login de allauth."""

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode

from .activacion import dias_vigencia, token_activacion


def _usuario_del_enlace(uidb64, token):
    try:
        usuario = get_user_model().objects.select_related("cliente").get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except (TypeError, ValueError, OverflowError, get_user_model().DoesNotExist):
        return None
    if not usuario.is_active or not token_activacion.check_token(usuario, token):
        return None
    return usuario


def activar_cuenta(request, uidb64, token):
    usuario = _usuario_del_enlace(uidb64, token)
    if usuario is None:
        return render(request, "account/activar_cuenta.html", {"enlace_invalido": True}, status=400)

    form = SetPasswordForm(usuario, request.POST or None)
    for campo in form.fields.values():
        campo.widget.attrs["autocomplete"] = "new-password"
    if request.method == "POST" and form.is_valid():
        form.save()
        from apps.core.models import RegistroAuditoria

        RegistroAuditoria.registrar(
            usuario=usuario,
            accion=RegistroAuditoria.Accion.EDITAR,
            entidad="usuario",
            entidad_id=usuario.pk,
            detalle=f"{usuario.username} · cuenta activada por la persona invitada",
        )
        login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
        nombre = usuario.first_name or usuario.email
        messages.success(request, f"¡Hola, {nombre}! Tu cuenta quedó activa. Desde ahora entras con tu correo y la contraseña que acabas de crear.")
        from .adapter import CuentaAdapter

        return redirect(CuentaAdapter(request).get_login_redirect_url(request))

    return render(request, "account/activar_cuenta.html", {"form": form, "usuario_invitado": usuario, "dias": dias_vigencia()})


def login_admin(request, extra_context=None):
    """Reemplaza el login propio del admin de Django (admin.site.login).

    Nunca recibe contraseñas: sin sesión se va al login de allauth (2FA, límite de intentos, auditoría);
    con sesión y permiso, al admin; con sesión pero sin permiso, a su propia vista.
    """
    from django.contrib import admin

    from apps.accounts.decorators import _redirigir_segun_rol

    destino = request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        destino = ""
    if not request.user.is_authenticated:
        return redirect_to_login(destino or request.path.replace("login/", ""))
    if admin.site.has_permission(request):
        return redirect(destino or "admin:index")
    messages.error(request, "No tienes acceso al administrador del sistema.")
    return redirect(_redirigir_segun_rol(request))
