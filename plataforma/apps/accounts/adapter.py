from allauth.account.adapter import DefaultAccountAdapter
from django.urls import reverse


class CuentaAdapter(DefaultAccountAdapter):
    """Reglas de cuentas de la plataforma (Documento de Alcance 4.3 y 5.1)."""

    def is_open_for_signup(self, request):
        # Las cuentas las crea la administradora (con su rol); no hay registro público.
        return False

    def get_login_redirect_url(self, request):
        # Equipo de la agencia → panel interno; clientes → portal.
        if request.user.is_staff:
            return reverse("crm:dashboard")
        return reverse("content:calendario")
