def _hay_novedades():
    from .models import Contenido

    return Contenido.objects.filter(estado=Contenido.Estado.PUBLICADO, seccion=Contenido.Seccion.NOVEDADES).exists()


def agencia(request):
    """Datos de la agencia para navbar, footer, formularios y cotización (todas las páginas).

    Nombre y dominio son fijos (Documento de Alcance). Correo, teléfono, WhatsApp, ciudad y redes vienen de
    Panel → Configuración (website.ConfiguracionAgencia); se leen solo si la plantilla los usa (una consulta).
    """
    from django.utils.functional import SimpleLazyObject

    novedades = {}

    def mostrar_novedades():
        # Se consulta una sola vez por página, y solo si la plantilla lo usa.
        if "hay" not in novedades:
            novedades["hay"] = _hay_novedades()
        return novedades["hay"]

    def datos():
        from .models import ConfiguracionAgencia

        config = ConfiguracionAgencia.actual()
        usuario_ig = config.instagram_usuario
        return {
            "nombre": "Agencia Cosmopolitan",
            "descriptor": "Marketing digital",
            "dominio": "agenciacosmopolitan.cl",
            "correo": config.correo,
            "telefono": config.telefono,
            "whatsapp": config.whatsapp,
            "ciudad": config.ciudad,
            # Redes: None = no se muestran en el sitio.
            "instagram": {"usuario": f"@{usuario_ig}", "url": f"https://instagram.com/{usuario_ig}"} if usuario_ig else None,
            "linkedin": {"nombre": config.linkedin_nombre or "LinkedIn", "url": config.linkedin_url} if config.linkedin_url else None,
            # El menú muestra «Casos» solo cuando haya casos reales publicados.
            "mostrar_casos": False,
            # «Novedades» aparece en el menú solo si hay al menos una entrada publicada (se consulta solo si se usa).
            "mostrar_novedades": mostrar_novedades,
        }

    return {"agencia": SimpleLazyObject(datos)}


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


def metadatos_pagina(request):
    """Metadatos SEO definidos en el CMS para la página fija que se está viendo (PC-SEO-01b).

    `seo_pagina` se resuelve solo si la plantilla lo usa (una consulta como máximo) y solo en las
    páginas fijas del sitio público; en el panel, el portal o el admin queda en None.
    """
    from .models import MetadatosPagina

    cache = {}

    def seo_pagina():
        if "valor" not in cache:
            match = getattr(request, "resolver_match", None)
            nombre = getattr(match, "url_name", None)
            if match is None or match.namespace != "website" or nombre not in MetadatosPagina.Pagina.values:
                cache["valor"] = None
            else:
                cache["valor"] = MetadatosPagina.objects.filter(pagina=nombre).first()
        return cache["valor"]

    return {"seo_pagina": seo_pagina}
