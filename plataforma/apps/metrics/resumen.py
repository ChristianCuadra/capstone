"""Indicadores de un cliente en un rango de fechas: los usa el dashboard de la agencia (PC-DSH-01),
el portal del cliente (PC-DSH-02) y el reporte mensual (PC-IA-02), así las cifras siempre coinciden."""

from collections import OrderedDict
from decimal import Decimal

from django.db.models import Sum

from .models import Fuente, MetricaDiaria

MESES_CORTOS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _div(a, b):
    return (Decimal(a) / Decimal(b)) if a is not None and b else None


def resumen_metricas(cliente, desde, hasta):
    qs = MetricaDiaria.all_objects.filter(cliente=cliente, fecha__gte=desde, fecha__lte=hasta).order_by("fecha")
    if not qs.exists():
        return {"hay_datos": False, "desde": desde, "hasta": hasta}

    tot = qs.aggregate(
        alcance=Sum("alcance"), impresiones=Sum("impresiones"), interacciones=Sum("interacciones"),
        clics=Sum("clics"), gasto=Sum("gasto"), resultados=Sum("resultados"),
    )
    con_seguidores = qs.filter(fuente=Fuente.INSTAGRAM, seguidores__isnull=False)
    primero_seg = con_seguidores.first()
    ultimo_seg = con_seguidores.last()
    seguidores = ultimo_seg.seguidores if ultimo_seg else None
    nuevos = (ultimo_seg.seguidores - primero_seg.seguidores) if (ultimo_seg and primero_seg) else None

    tasa = _div(tot["interacciones"], tot["alcance"])
    costo = _div(tot["gasto"], tot["resultados"])
    indicadores = [
        {"clave": "alcance", "nombre": "Alcance", "valor": tot["alcance"], "tipo": "entero"},
        {"clave": "impresiones", "nombre": "Impresiones", "valor": tot["impresiones"], "tipo": "entero"},
        {"clave": "interacciones", "nombre": "Interacciones", "valor": tot["interacciones"], "tipo": "entero"},
        {"clave": "tasa", "nombre": "Tasa de interacción", "valor": (tasa * 100).quantize(Decimal("0.1")) if tasa is not None else None, "tipo": "porcentaje", "ayuda": "Interacciones / alcance"},
        {"clave": "seguidores", "nombre": "Seguidores", "valor": seguidores, "tipo": "entero", "variacion": nuevos},
        {"clave": "clics", "nombre": "Clics", "valor": tot["clics"], "tipo": "entero"},
        {"clave": "gasto", "nombre": "Inversión en campañas", "valor": tot["gasto"], "tipo": "pesos"},
        {"clave": "resultados", "nombre": "Resultados", "valor": tot["resultados"], "tipo": "entero"},
        {"clave": "costo", "nombre": "Costo por resultado", "valor": costo.quantize(Decimal("1")) if costo is not None else None, "tipo": "pesos"},
    ]

    serie = OrderedDict()
    for m in qs:
        dia = serie.setdefault(m.fecha, {"alcance": 0, "interacciones": 0})
        dia["alcance"] += m.alcance or 0
        dia["interacciones"] += m.interacciones or 0

    meses = OrderedDict()
    for m in qs:
        clave = (m.fecha.year, m.fecha.month)
        fila = meses.setdefault(clave, {"mes": f"{MESES_CORTOS[m.fecha.month - 1]} {m.fecha.year}", "alcance": 0, "interacciones": 0, "gasto": Decimal(0), "resultados": 0})
        fila["alcance"] += m.alcance or 0
        fila["interacciones"] += m.interacciones or 0
        fila["gasto"] += m.gasto or 0
        fila["resultados"] += m.resultados or 0

    return {
        "hay_datos": True,
        "desde": desde,
        "hasta": hasta,
        "dias": qs.values("fecha").distinct().count(),
        "indicadores": [i for i in indicadores if i["valor"] is not None],
        "totales": tot,
        "seguidores": seguidores,
        "nuevos_seguidores": nuevos,
        "tasa_interaccion": tasa,
        "grafico": {
            "fechas": [f.strftime("%d-%m") for f in serie],
            "alcance": [v["alcance"] for v in serie.values()],
            "interacciones": [v["interacciones"] for v in serie.values()],
        },
        "por_mes": list(meses.values()),
    }
