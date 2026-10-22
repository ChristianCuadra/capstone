"""Activación de la cuenta del cliente desde el enlace de invitación (PC-AUT-07)."""

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.forms import SetPasswordForm
from django.shortcuts import redirect, render
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
