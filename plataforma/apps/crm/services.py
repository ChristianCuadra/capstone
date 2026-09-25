"""Reglas del cotizador: sugerencia de plan a partir de lo que el prospecto declaró (Alcance 5.3).

Es una regla determinística y explicable (no IA): el plan más barato que cubre lo pedido,
sin pasarse del presupuesto declarado. La decisión comercial final es de la agencia.
"""

from django.db import transaction

from apps.catalog.models import Plan

from .models import Interaccion, Prospecto

# Qué tipo de entregable (catalog.TipoEntregable.slug) exige cada objetivo del formulario.
# Supuesto inicial: ajustar con la agencia.
ENTREGABLE_POR_OBJETIVO = {
    "Vender más online": "gestion-de-publicidad",
    "Aumentar seguidores": "reel",
    "Posicionar la marca": "branding",
    "Generar leads B2B": "gestion-de-publicidad",
    "Ordenar el contenido": "calendario-de-contenido",
    "Mejorar el sitio web": "servicios-tecnicos-digitales",
    "SEO local": "servicios-tecnicos-digitales",
}

# Qué tipo de entregable cubre cada servicio suelto (catalog.Servicio.slug).
ENTREGABLE_POR_SERVICIO = {
    "asesorias-y-consultorias": "asesoria-estrategica",
    "branding-rebranding": "branding",
    "servicios-tecnicos-digitales": "servicios-tecnicos-digitales",
    "marketing-de-influencers": "marketing-de-influencers",
    "contenido-audiovisual": "reel",
    "diseno-grafico": "carrusel",
    "publicidad-ads": "gestion-de-publicidad",
}

# Tope mensual por rango de presupuesto (None = sin tope).
TOPE_POR_PRESUPUESTO = {
    "menos_150": 149999,
    "150_250": 250000,
    "250_350": 350000,
    "mas_350": None,
}


def entregables_requeridos(objetivos, servicio_slugs):
    requeridos = {ENTREGABLE_POR_OBJETIVO[o] for o in objetivos if o in ENTREGABLE_POR_OBJETIVO}
    requeridos |= {ENTREGABLE_POR_SERVICIO[s] for s in servicio_slugs if s in ENTREGABLE_POR_SERVICIO}
    return requeridos


def sugerir_plan(presupuesto, objetivos, servicio_slugs):
    """Devuelve el Plan sugerido, o None si el presupuesto no alcanza ningún plan (servicios sueltos)."""
    planes = list(Plan.objects.filter(activo=True).prefetch_related("tipos_entregable").order_by("precio_mensual"))
    if not planes:
        return None

    requeridos = entregables_requeridos(objetivos, servicio_slugs)
    tope = TOPE_POR_PRESUPUESTO.get(presupuesto)
    dentro_del_presupuesto = [p for p in planes if tope is None or p.precio_mensual <= tope]

    cubren = [p for p in planes if requeridos <= {t.slug for t in p.tipos_entregable.all()}]
    candidato = cubren[0] if cubren else planes[-1]

    if tope is None or candidato.precio_mensual <= tope:
        return candidato
    # Lo pedido excede el presupuesto: el plan más completo que sí cabe.
    return dentro_del_presupuesto[-1] if dentro_del_presupuesto else None


@transaction.atomic
def registrar_solicitud(form, plan_interes=None):
    """Crea el Prospecto desde el formulario del sitio, le sugiere un plan y abre su historial."""
    prospecto = form.save(commit=False)
    prospecto.canal = Prospecto.Canal.FORMULARIO_SITIO
    prospecto.plan_interes = plan_interes
    prospecto.save()
    form.save_m2m()

    servicio_slugs = [s.slug for s in prospecto.servicios_requeridos.all()]
    prospecto.plan_sugerido = sugerir_plan(prospecto.presupuesto, prospecto.objetivos, servicio_slugs)
    prospecto.save(update_fields=["plan_sugerido"])

    Interaccion.objects.create(
        prospecto=prospecto,
        tipo=Interaccion.Tipo.SISTEMA,
        titulo="Solicitud recibida desde el sitio",
        descripcion=(
            f"Presupuesto: {prospecto.get_presupuesto_display()}. "
            f"Plan sugerido por el cotizador: {prospecto.plan_sugerido.nombre if prospecto.plan_sugerido else 'servicios sueltos'}."
        ),
    )
    # TODO: notificación "Nuevo prospecto registrado" por correo al equipo (Alcance 5.10) cuando haya EMAIL_API_KEY.
    return prospecto
