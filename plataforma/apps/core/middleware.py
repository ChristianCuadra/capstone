from .access import ids_permitidos
from .context import (
    reset_allowed_client_ids,
    reset_current_client_id,
    set_allowed_client_ids,
    set_current_client_id,
)

SESSION_CLIENT_KEY = "client_id"


class TenantMiddleware:
    """Publica, durante la petición, qué clientes puede ver el usuario y cuál es el cliente activo.

    - Cliente aprobador / lector: solo su empresa, que además es siempre la activa. No se guarda
      en sesión, así nadie puede cambiar de cliente manipulándola.
    - Colaboradora: solo sus clientes asignados. El cliente activo es el que eligió en el selector
      del panel (se guarda en sesión) y se descarta si ya no está entre sus asignados.
    - Administradora y personal sin rol: ven todos los clientes. El activo es el elegido en el
      selector, o ninguno (sin filtrar).
    - Sesión sin iniciar u otro rol: ningún cliente.

    Los modelos que heredan de TenantModel se filtran solos con esta información.
    Debe ir después de SessionMiddleware y AuthenticationMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        permitidos = ids_permitidos(user)

        client_id = None
        if user.is_authenticated:
            if user.es_cliente:
                client_id = user.cliente_id
            else:
                elegido = request.session.get(SESSION_CLIENT_KEY)
                if elegido is not None and (permitidos is None or elegido in permitidos):
                    client_id = elegido
                elif elegido is not None:
                    request.session.pop(SESSION_CLIENT_KEY, None)
        request.client_id = client_id
        request.clientes_permitidos = permitidos

        token_cliente = set_current_client_id(client_id)
        token_permitidos = set_allowed_client_ids(permitidos)
        try:
            return self.get_response(request)
        finally:
            reset_allowed_client_ids(token_permitidos)
            reset_current_client_id(token_cliente)
