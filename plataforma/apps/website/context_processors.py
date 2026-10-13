def _hay_novedades():
    from .models import Contenido

    return Contenido.objects.filter(estado=Contenido.Estado.PUBLICADO, seccion=Contenido.Seccion.NOVEDADES).exists()


def agencia(request):
    novedades = {}

    def mostrar_novedades():
        # Se consulta una sola vez por página, y solo si la plantilla lo usa.
        if "hay" not in novedades:
            novedades["hay"] = _hay_novedades()
        return novedades["hay"]

    """Datos de contacto de la agencia, usados en navbar y footer de todas las páginas."""
    # TODO: Supabase - tabla agencia_config (fila única, editable desde "Contenido del sitio")
    # Nombre y dominio según el Documento de Alcance. Correo y teléfono: por confirmar con la agencia.
    return {
        "agencia": {
            "nombre": "Agencia Cosmopolitan",
            "descriptor": "Marketing digital",
            "dominio": "agenciacosmopolitan.cl",
            "correo": "hola@agenciacosmopolitan.cl",
            "telefono": "+56 9 8765 4321",
            # WhatsApp: el mismo número, solo dígitos (link wa.me). Ficticio hasta que la agencia entregue el real.
            "whatsapp": "56987654321",
            # Redes: None = no se muestran. Completar con las URLs reales cuando la agencia las confirme.
            "instagram": None,  # {"usuario": "@…", "url": "https://instagram.com/…"}
            "linkedin": None,  # {"nombre": "…", "url": "https://linkedin.com/company/…"}
            "ciudad": "Santiago, Chile",
            # El menú muestra «Casos» solo cuando haya casos reales publicados.
            "mostrar_casos": False,
            # «Novedades» aparece en el menú solo si hay al menos una entrada publicada (se consulta solo si se usa).
            "mostrar_novedades": mostrar_novedades,
        }
    }


def analitica(request):
    """IDs de analitica (GA4/GTM/Meta Pixel), leidos desde variables de entorno (PC-SEO-02).

    Vacios por defecto: mientras la agencia no confirme sus cuentas, el sitio no carga
    ninguna etiqueta de seguimiento (ver _analitica.html, que solo las inyecta si hay consentimiento).
    """
    from django.conf import settings

    return {
        "ga4_id": settings.GA4_MEASUREMENT_ID,
        "gtm_id": settings.GTM_CONTAINER_ID,
        "meta_pixel_id": settings.META_PIXEL_ID,
    }
