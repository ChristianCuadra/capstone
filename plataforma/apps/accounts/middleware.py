"""2FA obligatorio para el equipo de la agencia (PC-AUT-02, Ley 21.719: medidas de seguridad).

La administradora y las colaboradoras ven datos personales de todos los clientes y prospectos. Si alguien
del equipo entra al panel (/panel/) o al admin de Django (/admin/) sin la app autenticadora configurada,
se le lleva a configurarla. El resto del sitio (portal, sitio público, páginas de cuenta y de 2FA) no se
toca, así nadie queda atrapado: siempre puede configurar el 2FA o cerrar sesión.
"""

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect

RUTAS_PROTEGIDAS = ("/panel/", "/admin/")
MENSAJE_CONFIGURAR_2FA = (
    "Por seguridad, el equipo de la agencia debe activar la verificación en dos pasos antes de entrar al panel. "
    "Escanea el código con tu app autenticadora (Google Authenticator, Microsoft Authenticator u otra)."
)


class Exigir2FAEquipoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "EXIGIR_2FA_EQUIPO", False) and request.path.startswith(RUTAS_PROTEGIDAS):
            from allauth.mfa.utils import is_mfa_enabled

            from apps.core.access import es_equipo

            user = request.user
            if user.is_authenticated and es_equipo(user) and not is_mfa_enabled(user):
                messages.warning(request, MENSAJE_CONFIGURAR_2FA)
                return redirect("mfa_activate_totp")
        return self.get_response(request)
