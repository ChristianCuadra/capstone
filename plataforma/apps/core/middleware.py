from .context import reset_current_client_id, set_current_client_id

SESSION_CLIENT_KEY = "client_id"


class TenantMiddleware:
    """Publica el cliente activo de la sesión en un ContextVar durante la petición.

    Debe ir después de SessionMiddleware y AuthenticationMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        client_id = None
        if request.user.is_authenticated:
            client_id = request.session.get(SESSION_CLIENT_KEY)
        request.client_id = client_id

        token = set_current_client_id(client_id)
        try:
            return self.get_response(request)
        finally:
            reset_current_client_id(token)
