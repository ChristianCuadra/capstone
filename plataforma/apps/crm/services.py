"""Reglas del cotizador: sugerencia de plan a partir de lo que el prospecto declaró (Alcance 5.3).

Es una regla determinística y explicable (no IA): el plan más barato que cubre lo pedido,
sin pasarse del presupuesto declarado. La decisión comercial final es de la agencia.
"""

import logging

from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Plan
from apps.website.privacidad import VERSION_POLITICA

from .models import Interaccion, Prospecto

logger = logging.getLogger(__name__)

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


# ── Origen de la visita y prospectos ya existentes ─────────────────────────

CAMPOS_ORIGEN = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "pagina_entrada", "sitio_referencia")


def aplicar_origen(prospecto, origen):
    """Copia al prospecto el origen de la visita guardado en la sesión (PC-CAP-01).

    Solo si el prospecto todavía no tiene origen: así se conserva la campaña por la que llegó la primera vez.
    """
    if not origen or prospecto.tiene_origen:
        return
    for campo in CAMPOS_ORIGEN:
        setattr(prospecto, campo, (origen.get(campo) or "")[: Prospecto._meta.get_field(campo).max_length])


def buscar_prospecto_abierto(correo):
    """Prospecto en curso con ese correo (sin convertir en cliente, ni ganado ni perdido), o None.

    Permite que quien pidió la asesoría gratuita y después cotiza siga siendo el mismo prospecto,
    sin duplicar sus datos.
    """
    if not correo:
        return None
    return (
        Prospecto.objects.filter(correo__iexact=correo.strip(), cliente__isnull=True)
        .exclude(etapa__in=[Prospecto.Etapa.GANADO, Prospecto.Etapa.PERDIDO])
        .order_by("-creado_en")
        .first()
    )


def completar_prospecto(prospecto, datos, campos):
    """Completa solo los campos vacíos del prospecto con lo que llegó desde un formulario público.

    Los formularios del sitio no exigen sesión: quien escriba el correo de otro prospecto no debe poder
    reemplazar sus datos. Lo que llegue distinto de lo ya registrado no se aplica; se devuelve como texto
    para dejarlo en el historial y que el equipo decida si lo actualiza.
    """
    distintos = []
    for campo in campos:
        nuevo = datos.get(campo)
        if nuevo in (None, "", []):
            continue
        actual = getattr(prospecto, campo)
        if actual in (None, "", []):
            setattr(prospecto, campo, nuevo)
        elif actual != nuevo:
            etiqueta = Prospecto._meta.get_field(campo).verbose_name
            distintos.append(f"{etiqueta}: «{nuevo}»")
    return distintos


def _nota_distintos(distintos):
    if not distintos:
        return ""
    return " Datos enviados distintos a los registrados (no se aplicaron; revisar): " + "; ".join(distintos) + "."


def _nota_consentimiento():
    """Constancia del consentimiento (Ley 21.719): qué versión de la política aceptó; la fecha es la de la entrada."""
    return f" Aceptó la política de privacidad (versión {VERSION_POLITICA})."


@transaction.atomic
def registrar_solicitud(form, plan_interes=None, origen=None):
    """Crea (o completa) el Prospecto desde el formulario de cotización, le sugiere un plan y abre su historial.

    Si la persona ya había pedido la asesoría gratuita con el mismo correo, se completa ese mismo prospecto
    (solo los campos vacíos, ver completar_prospecto).
    """
    existente = buscar_prospecto_abierto(form.cleaned_data.get("correo"))
    distintos = []
    if existente:
        prospecto = existente
        excluidos = ("servicios_requeridos", "correo", "acepta_privacidad")
        campos = [c for c in form._meta.fields if c in form.cleaned_data and c not in excluidos]
        distintos = completar_prospecto(prospecto, form.cleaned_data, campos)
        prospecto.acepta_privacidad = True  # el formulario lo exige
        prospecto.plan_interes = prospecto.plan_interes or plan_interes
        aplicar_origen(prospecto, origen)
        prospecto.save()
        prospecto.servicios_requeridos.add(*(form.cleaned_data.get("servicios_requeridos") or []))
    else:
        prospecto = form.save(commit=False)
        prospecto.canal = Prospecto.Canal.FORMULARIO_SITIO
        prospecto.plan_interes = plan_interes
        aplicar_origen(prospecto, origen)
        prospecto.save()
        form.save_m2m()

    servicio_slugs = [s.slug for s in prospecto.servicios_requeridos.all()]
    prospecto.plan_sugerido = sugerir_plan(prospecto.presupuesto, prospecto.objetivos, servicio_slugs)
    prospecto.save(update_fields=["plan_sugerido"])

    Interaccion.objects.create(
        prospecto=prospecto,
        tipo=Interaccion.Tipo.SISTEMA,
        titulo="Cotización solicitada desde el sitio" if existente else "Solicitud recibida desde el sitio",
        descripcion=(
            f"Presupuesto: {prospecto.get_presupuesto_display()}. "
            f"Plan sugerido por el cotizador: {prospecto.plan_sugerido.nombre if prospecto.plan_sugerido else 'servicios sueltos'}."
            + (" Completó la cotización después de pedir la asesoría gratuita: se completaron sus datos." if existente else "")
            + _nota_distintos(distintos)
            + _nota_consentimiento()
        ),
    )
    # TODO: notificación "Nuevo prospecto registrado" por correo al equipo (Alcance 5.10) cuando haya EMAIL_API_KEY.
    return prospecto


@transaction.atomic
def registrar_asesoria(form, origen=None):
    """Guarda la solicitud de asesoría gratuita como prospecto (canal «Asesoría gratuita»).

    Así el caso no se pierde aunque el correo falle, y si después cotiza o contrata, sus datos ya están cargados.
    """
    caso = form.cleaned_data["situacion_actual"]
    prospecto = buscar_prospecto_abierto(form.cleaned_data["correo"])
    distintos = []
    if prospecto:
        distintos = completar_prospecto(
            prospecto, form.cleaned_data, ("nombre", "empresa", "telefono", "rubro", "region", "tamano", "instagram")
        )
        if not prospecto.situacion_actual:
            prospecto.situacion_actual = caso
        aplicar_origen(prospecto, origen)
        prospecto.save()
    else:
        prospecto = form.save(commit=False)
        prospecto.canal = Prospecto.Canal.ASESORIA
        aplicar_origen(prospecto, origen)
        prospecto.save()

    Interaccion.objects.create(
        prospecto=prospecto,
        tipo=Interaccion.Tipo.SISTEMA,
        titulo="Pidió la asesoría gratuita desde el sitio",
        descripcion=f"Su caso: {caso}" + _nota_distintos(distintos) + _nota_consentimiento(),
    )
    return prospecto


def notificar_asesoria(prospecto, caso, correo_agencia, url_ficha=""):
    """Envía el caso de la asesoría gratuita al correo de la agencia.

    Si el correo aún no está configurado en producción (ver tarjeta de Trello), no se cae el sitio:
    el caso igual queda guardado en el panel como prospecto.
    """
    cuerpo = "\n".join([
        "Nueva solicitud de asesoría gratuita desde el sitio.",
        "",
        f"Nombre: {prospecto.nombre}",
        f"Empresa o marca: {prospecto.empresa}",
        f"Correo: {prospecto.correo}",
        f"Teléfono: {prospecto.telefono or '—'}",
        f"Rubro: {prospecto.rubro} · Región: {prospecto.region} · Tamaño: {prospecto.get_tamano_display() or '—'}",
        f"Instagram: @{prospecto.instagram}" if prospecto.instagram else "Instagram: —",
        "",
        "Su caso:",
        caso,
        "",
        f"Ver en el panel: {url_ficha}" if url_ficha else "",
    ])
    try:
        send_mail(f"Asesoría gratuita: {prospecto.empresa}", cuerpo, None, [correo_agencia])
        return True
    except Exception:  # noqa: BLE001 - el correo nunca debe impedir guardar la solicitud
        logger.exception("No se pudo enviar el correo de la asesoría gratuita (prospecto %s)", prospecto.pk)
        return False


# ── Derechos de las personas (Ley 21.719) ─────────────────────────────────────

def _valor_json(valor):
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    if hasattr(valor, "pk"):
        return str(valor)
    return valor


def datos_personales_prospecto(prospecto):
    """Todo lo que la plataforma guarda de una persona (derecho de acceso y portabilidad)."""
    ficha = {}
    for campo in prospecto._meta.concrete_fields:
        valor = getattr(prospecto, campo.name)
        ficha[campo.verbose_name] = _valor_json(valor)
    return {
        "responsable": "Agencia Cosmopolitan",
        "generado_en": _valor_json(timezone.now()),
        "ficha": ficha,
        "servicios_de_interes": [s.nombre for s in prospecto.servicios_requeridos.all()],
        "historial": [
            {"fecha": _valor_json(i.creado_en), "tipo": i.get_tipo_display(), "titulo": i.titulo, "detalle": i.descripcion}
            for i in prospecto.interacciones.all()
        ],
        "cotizaciones": [
            {"numero": c.numero, "estado": c.get_estado_display(), "contacto": c.contacto, "creada": _valor_json(c.creado_en)}
            for c in prospecto.cotizaciones.all()
        ],
    }


@transaction.atomic
def anonimizar_prospecto(prospecto, usuario):
    """Derecho de supresión: borra lo que identifica a la persona y conserva las cifras (etapa, plan, montos)
    para las estadísticas comerciales, sin forma de saber de quién eran."""
    prospecto.nombre = "Datos eliminados"
    prospecto.empresa = f"Prospecto anonimizado #{prospecto.pk}"
    prospecto.rut = ""
    prospecto.correo = f"anonimizado-{prospecto.pk}@eliminado.invalid"
    prospecto.telefono = ""
    prospecto.instagram = ""
    prospecto.instagram_seguidores = None
    prospecto.sitio_web = ""
    prospecto.redes_actuales = []
    prospecto.situacion_actual = ""
    prospecto.diagnostico_ia = ""
    prospecto.pagina_entrada = ""
    prospecto.sitio_referencia = ""
    prospecto.utm_term = ""
    prospecto.utm_content = ""
    prospecto.save()
    # Notas, correos registrados y tareas pueden nombrar a la persona: se eliminan.
    prospecto.interacciones.all().delete()
    prospecto.tareas.all().delete()
    prospecto.cotizaciones.update(contacto="", diagnostico="")
    Interaccion.objects.create(
        prospecto=prospecto,
        tipo=Interaccion.Tipo.SISTEMA,
        titulo="Datos personales eliminados",
        descripcion="Se eliminaron los datos que identificaban a la persona, a su solicitud (Ley 21.719).",
        autor=usuario,
    )
