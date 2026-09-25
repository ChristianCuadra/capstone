"""Consultas del catálogo para el sitio público y el cotizador.

Devuelven diccionarios con la misma forma que usaban los templates cuando el contexto estaba hardcodeado.
"""

from django.db.models import Prefetch

from .models import Plan, PlanEntregable, Servicio, TipoEntregable

# Se concatena directo al precio: "$35.000/hora", "$70.000 pago único".
SUFIJO_PRECIO = {
    Servicio.ModalidadCobro.POR_HORA: "/hora",
    Servicio.ModalidadCobro.PAGO_UNICO: " pago único",
    Servicio.ModalidadCobro.POR_CAMPANA: " por campaña",
    Servicio.ModalidadCobro.POR_PAQUETE: "",
    Servicio.ModalidadCobro.MENSUAL: "/mes",
}


def planes_del_sitio():
    entregables = PlanEntregable.objects.select_related("tipo_entregable")
    planes = (
        Plan.objects.filter(activo=True, visible_en_sitio=True)
        .prefetch_related(Prefetch("entregables", queryset=entregables))
    )
    return [
        {
            "slug": plan.slug,
            "nombre": plan.nombre,
            "descripcion": plan.descripcion,
            "precio_mensual": plan.precio_mensual,
            "precio_primer_mes": plan.precio_primer_mes,
            "destacado": plan.destacado,
            "badge": plan.etiqueta,
            "incluye": [e.texto for e in plan.entregables.all()],
            # {id de tipo de entregable: cantidad o True}, para la tabla comparativa
            "_por_tipo": {e.tipo_entregable_id: e.cantidad_mensual or True for e in plan.entregables.all()},
        }
        for plan in planes
    ]


def comparativa_de_planes(planes):
    """Filas de la tabla comparativa: una por tipo de entregable presente en algún plan.

    Cada valor es la cantidad mensual, True (incluido sin cuota) o False (no incluido).
    """
    ids = {tipo_id for plan in planes for tipo_id in plan["_por_tipo"]}
    tipos = TipoEntregable.objects.filter(id__in=ids)
    return [
        {
            "caracteristica": f"{tipo.nombre_plural or tipo.nombre} al mes" if tipo.tiene_cuota else tipo.nombre,
            "celdas": [
                {"valor": plan["_por_tipo"].get(tipo.id, False), "destacado": plan["destacado"]}
                for plan in planes
            ],
        }
        for tipo in tipos
    ]


def servicios_del_sitio():
    return [
        {
            "slug": s.slug,
            "nombre": s.nombre,
            "descripcion": s.descripcion,
            "precio": s.precio,
            "modalidad": s.modalidad_cobro,
            "sufijo_precio": SUFIJO_PRECIO[s.modalidad_cobro],
        }
        for s in Servicio.objects.filter(activo=True, visible_en_sitio=True)
    ]
