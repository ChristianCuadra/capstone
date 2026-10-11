"""Origen de la visita para medir campañas (PC-CAP-01: el prospecto se crea "con su origen (UTM)").

Cuando alguien entra al sitio público desde un link de campaña (…?utm_source=instagram&utm_campaign=octubre)
o desde otro sitio (Google, Instagram, un blog), se guarda en su sesión de dónde vino y por qué página entró.
Si después envía la cotización o pide la asesoría, ese origen queda grabado en el prospecto
(crm.services.aplicar_origen). Las visitas directas no crean sesión ni guardan nada.
"""

from urllib.parse import urlparse

CLAVE_SESION = "origen_visita"
PARAMETROS_UTM = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content")
# Zonas privadas: ahí no se mide nada (equipo, clientes, admin y archivos).
PREFIJOS_EXCLUIDOS = ("/panel/", "/portal/", "/admin/", "/accounts/", "/static/", "/media/")
LARGOS = {"utm_source": 100, "utm_medium": 100, "utm_campaign": 150, "utm_term": 150, "utm_content": 150,
          "pagina_entrada": 300, "sitio_referencia": 300}


def _referencia_externa(request):
    """URL del sitio desde el que llegó la visita, o '' si viene del mismo sitio o no se sabe."""
    referencia = request.META.get("HTTP_REFERER", "")
    if not referencia:
        return ""
    host = urlparse(referencia).netloc.lower()
    if not host or host == request.get_host().lower():
        return ""
    return referencia


class OrigenVisitaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "GET" and not request.path.startswith(PREFIJOS_EXCLUIDOS):
            self._capturar(request)
        return self.get_response(request)

    def _capturar(self, request):
        utm = {p: request.GET.get(p, "").strip() for p in PARAMETROS_UTM}
        referencia = _referencia_externa(request)
        if not any(utm.values()) and not referencia:
            return  # navegación interna o visita directa: se conserva el origen que ya hubiera
        if not any(utm.values()) and CLAVE_SESION in request.session:
            return  # un link sin campaña no reemplaza una campaña ya registrada en esta visita
        origen = {**utm, "pagina_entrada": request.get_full_path(), "sitio_referencia": referencia}
        request.session[CLAVE_SESION] = {k: v[: LARGOS[k]] for k, v in origen.items()}
