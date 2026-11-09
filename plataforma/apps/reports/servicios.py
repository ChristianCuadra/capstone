"""Datos que alimentan el reporte mensual: los mismos del dashboard y del cumplimiento del plan."""

import calendar
from datetime import date

from apps.content.cumplimiento import cumplimiento_cliente
from apps.metrics.resumen import resumen_metricas

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def mes_texto(primero):
    return f"{MESES[primero.month - 1]} {primero.year}"


def datos_del_mes(cliente, primero):
    ultimo = date(primero.year, primero.month, calendar.monthrange(primero.year, primero.month)[1])
    return resumen_metricas(cliente, primero, ultimo), cumplimiento_cliente(cliente, primero)


def _valor(indicador):
    valor = indicador["valor"]
    if indicador["tipo"] == "porcentaje":
        return f"{valor} %".replace(".", ",")
    texto = f"{valor:,.0f}".replace(",", ".")
    return f"${texto}" if indicador["tipo"] == "pesos" else texto


def borrador_sin_ia(cliente, primero, resumen, cumplimiento):
    """Plantilla para escribir el reporte a mano cuando la IA no está disponible."""
    lineas = ["1. Resumen del mes", f"Durante {mes_texto(primero)} ...", "", "2. Resultados destacados"]
    if resumen.get("hay_datos"):
        for i in resumen["indicadores"]:
            lineas.append(f"- {i['nombre']}: {_valor(i)}")
    else:
        lineas.append("- (No hay métricas cargadas para este mes.)")
    lineas += ["", "3. Contenido entregado"]
    for f in (cumplimiento or {}).get("filas", []):
        lineas.append(f"- {f['tipo']}: {f['entregado']} de {f['comprometido']} entregados, {f['aprobado']} aprobados.")
    lineas += ["", "4. Recomendaciones para el próximo mes", "- ..."]
    return "\n".join(lineas)
