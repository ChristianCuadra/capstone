"""Datos personales de un cliente: acceso y portabilidad (PDF y JSON) y supresión (anonimizar). Ley 21.719.

La supresión borra lo que identifica a la empresa y a sus personas, y conserva solo cifras sin identificar
(plan, rubro, región, fechas del contrato, métricas y conteo de piezas) para las estadísticas de la agencia.
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.content.models import ComentarioPieza, HistorialVersionPieza, PiezaContenido, Solicitud
from apps.crm.services import _valor_json, anonimizar_prospecto, datos_personales_prospecto
from apps.reports.models import ReporteMensual

from .models import DocumentoCliente

logger = logging.getLogger(__name__)

CAMPOS_FICHA = [
    "nombre", "activo", "rut", "rubro", "region", "contacto_nombre", "contacto_correo", "contacto_telefono",
    "plan", "fecha_inicio_contrato", "forma_pago", "directrices_marca", "objetivos", "creado_en",
]


def datos_personales_cliente(cliente):
    ficha = {cliente._meta.get_field(c).verbose_name: _valor_json(getattr(cliente, c)) for c in CAMPOS_FICHA}
    datos = {
        "responsable": "Agencia Cosmopolitan",
        "generado_en": _valor_json(timezone.now()),
        "ficha": ficha,
        "usuarios_del_portal": [
            {
                "nombre": u.get_full_name() or "-",
                "correo": u.email,
                "rol": u.get_rol_display(),
                "activo": u.is_active,
                "último acceso": _valor_json(u.last_login) if u.last_login else "-",
            }
            for u in cliente.usuarios.all()
        ],
        "documentos": [
            {"nombre": d.nombre, "tipo": d.get_tipo_display(), "subido": _valor_json(d.creado_en)}
            for d in DocumentoCliente.all_objects.filter(cliente=cliente)
        ],
        "solicitudes": [
            {"asunto": s.asunto, "estado": s.get_estado_display(), "creada": _valor_json(s.creado_en), "mensajes": s.mensajes.count()}
            for s in Solicitud.all_objects.filter(cliente=cliente)
        ],
        "piezas_de_contenido": PiezaContenido.all_objects.filter(cliente=cliente).count(),
        "reportes_mensuales": [
            {"mes": r.mes.strftime("%m-%Y"), "estado": r.get_estado_display()}
            for r in ReporteMensual.all_objects.filter(cliente=cliente)
        ],
    }
    prospecto = getattr(cliente, "prospecto", None)
    if prospecto is not None and hasattr(prospecto, "pk"):
        datos["ficha_comercial_de_origen"] = datos_personales_prospecto(prospecto)["ficha"]
    return datos


def _borrar_archivo(campo):
    if not campo:
        return
    try:
        campo.delete(save=False)
    except Exception:  # el registro se borra igual; un archivo huérfano no debe impedir la supresión
        logger.exception("No se pudo borrar el archivo %s", campo.name)


@transaction.atomic
def anonimizar_cliente(cliente, usuario):
    """Supresión de datos del cliente. Requiere el cliente desactivado (lo valida la vista)."""
    pk = cliente.pk
    # Documentos, solicitudes con sus archivos y reportes: texto libre y archivos que identifican a la empresa.
    for documento in DocumentoCliente.all_objects.filter(cliente=cliente):
        _borrar_archivo(documento.archivo)
        documento.delete()
    for solicitud in Solicitud.all_objects.filter(cliente=cliente).prefetch_related("mensajes__archivos"):
        for mensaje in solicitud.mensajes.all():
            for archivo in mensaje.archivos.all():
                _borrar_archivo(archivo.archivo)
        solicitud.delete()
    ReporteMensual.all_objects.filter(cliente=cliente).delete()

    # Piezas: se conservan fecha, red, tipo y estado (cumplimiento histórico) sin su contenido.
    piezas = PiezaContenido.all_objects.filter(cliente=cliente)
    for pieza in piezas:
        _borrar_archivo(pieza.archivo)
    ComentarioPieza.objects.filter(pieza__in=piezas).delete()
    HistorialVersionPieza.objects.filter(pieza__in=piezas).delete()
    for pieza in piezas:
        pieza.titulo = f"Pieza #{pieza.pk}"
        pieza.texto = ""
        pieza.archivo = None
        pieza.save(update_fields=["titulo", "texto", "archivo", "actualizado_en"])

    # Cuentas del portal: son datos de personas.
    cliente.usuarios.all().delete()

    prospecto = getattr(cliente, "prospecto", None)
    if prospecto is not None and hasattr(prospecto, "pk"):
        anonimizar_prospecto(prospecto, usuario)

    cliente.nombre = f"Cliente anonimizado #{pk}"
    cliente.rut = ""
    cliente.contacto_nombre = ""
    cliente.contacto_correo = ""
    cliente.contacto_telefono = ""
    cliente.directrices_marca = ""
    cliente.objetivos = ""
    cliente.activo = False
    cliente.save()
    return cliente
