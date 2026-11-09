"""Cumplimiento del plan contratado (PC-CUM-01 para la agencia y PC-CUM-02 para el cliente).

Una sola función calcula los números, así la vista de la agencia y la del cliente siempre coinciden
y salen del calendario editorial (criterio 3 de ambas historias).

Reglas, por cada entregable con cuota mensual del plan (historias, carruseles, reels...):
- Comprometido: la cantidad mensual del plan.
- Entregado: piezas del mes de ese tipo que ya se le mostraron al cliente (en revisión, aprobadas o publicadas).
- Aprobado: piezas del mes de ese tipo aprobadas o publicadas.
- Programado: piezas del mes de ese tipo en cualquier estado salvo rechazado (incluye borradores).

Estado de cada entregable:
- Cumplido: entregado >= comprometido.
- Incumplido: el mes ya terminó y no se alcanzó lo comprometido.
- En riesgo: mes en curso y (lo programado no alcanza lo comprometido, o lo entregado va por debajo
  de lo esperado a la fecha según los días transcurridos del mes).
- Al día: el resto (también un mes futuro con todo programado).
"""

import calendar
import math

from django.utils import timezone

from .models import EstadoPieza, PiezaContenido

ESTADOS_ENTREGADOS = [EstadoPieza.EN_REVISION, EstadoPieza.APROBADO, EstadoPieza.PUBLICADO]
ESTADOS_APROBADOS = [EstadoPieza.APROBADO, EstadoPieza.PUBLICADO]

ORDEN_ESTADO = {"incumplido": 0, "en_riesgo": 1, "al_dia": 2, "cumplido": 3, "sin_plan": 4}
ETIQUETAS_ESTADO = {
    "incumplido": "Incumplido",
    "en_riesgo": "En riesgo",
    "al_dia": "Al día",
    "cumplido": "Cumplido",
    "sin_plan": "Sin plan con cuota",
}


def _avance_del_mes(primero, hoy):
    """Fracción del mes transcurrida: 0 si es futuro, 1 si ya terminó."""
    dias = calendar.monthrange(primero.year, primero.month)[1]
    if (hoy.year, hoy.month) < (primero.year, primero.month):
        return 0.0
    if (hoy.year, hoy.month) > (primero.year, primero.month):
        return 1.0
    return hoy.day / dias


def cumplimiento_cliente(cliente, primero, hoy=None):
    hoy = hoy or timezone.localdate()
    avance = _avance_del_mes(primero, hoy)
    mes_terminado = avance >= 1.0 and (hoy.year, hoy.month) != (primero.year, primero.month)

    piezas = PiezaContenido.all_objects.filter(
        cliente=cliente, fecha_programada__year=primero.year, fecha_programada__month=primero.month
    ).exclude(estado=EstadoPieza.RECHAZADO)
    conteo = {}
    sin_tipo = 0
    for tipo_id, estado in piezas.values_list("tipo_entregable_id", "estado"):
        if tipo_id is None:
            if estado in ESTADOS_ENTREGADOS:
                sin_tipo += 1
            continue
        c = conteo.setdefault(tipo_id, {"programado": 0, "entregado": 0, "aprobado": 0})
        c["programado"] += 1
        c["entregado"] += estado in ESTADOS_ENTREGADOS
        c["aprobado"] += estado in ESTADOS_APROBADOS

    filas = []
    plan = cliente.plan
    if plan:
        for pe in plan.entregables.select_related("tipo_entregable").filter(tipo_entregable__tiene_cuota=True):
            comprometido = pe.cantidad_mensual or 0
            c = conteo.get(pe.tipo_entregable_id, {"programado": 0, "entregado": 0, "aprobado": 0})
            esperado = math.floor(comprometido * avance)
            if c["entregado"] >= comprometido:
                estado = "cumplido"
            elif mes_terminado:
                estado = "incumplido"
            elif avance > 0 and (c["programado"] < comprometido or c["entregado"] < esperado):
                estado = "en_riesgo"
            else:
                estado = "al_dia"
            filas.append({
                "tipo": (pe.tipo_entregable.nombre_plural or pe.tipo_entregable.nombre).capitalize(),
                "comprometido": comprometido,
                "programado": c["programado"],
                "entregado": c["entregado"],
                "aprobado": c["aprobado"],
                "esperado": esperado,
                "faltan": max(comprometido - c["entregado"], 0),
                "porcentaje": round(100 * min(c["entregado"], comprometido) / comprometido) if comprometido else 100,
                "estado": estado,
                "etiqueta": ETIQUETAS_ESTADO[estado],
            })

    estado_general = min((f["estado"] for f in filas), key=ORDEN_ESTADO.get) if filas else "sin_plan"
    comprometido = sum(f["comprometido"] for f in filas)
    entregado = sum(min(f["entregado"], f["comprometido"]) for f in filas)
    return {
        "cliente": cliente,
        "plan": plan,
        "filas": filas,
        "sin_tipo": sin_tipo,
        "comprometido": comprometido,
        "entregado": sum(f["entregado"] for f in filas),
        "aprobado": sum(f["aprobado"] for f in filas),
        "porcentaje": round(100 * entregado / comprometido) if comprometido else None,
        "estado": estado_general,
        "etiqueta": ETIQUETAS_ESTADO[estado_general],
        "en_riesgo": estado_general in ("incumplido", "en_riesgo"),
    }


def cumplimiento_clientes(clientes, primero, hoy=None):
    """Cumplimiento de varios clientes, con los en riesgo o incumplidos primero."""
    datos = [cumplimiento_cliente(c, primero, hoy) for c in clientes.select_related("plan")]
    return sorted(datos, key=lambda d: (ORDEN_ESTADO[d["estado"]], d["cliente"].nombre.lower()))
