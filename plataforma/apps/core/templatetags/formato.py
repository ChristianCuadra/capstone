"""Filtros de formato chileno: los montos viajan como enteros y se formatean solo al mostrarse."""

import re

from django import template

register = template.Library()


def _miles(valor):
    return f"{int(valor):,}".replace(",", ".")


@register.filter
def miles(valor):
    """84320 -> '84.320'"""
    if valor in (None, ""):
        return ""
    return _miles(valor)


@register.filter
def absoluto(valor):
    """-3.1 -> 3.1 (el signo se comunica con ▲/▼ en el template)."""
    return abs(valor)


@register.filter
def clp(valor):
    """390000 -> '$390.000'"""
    if valor in (None, ""):
        return ""
    signo = "-" if int(valor) < 0 else ""
    return f"{signo}${_miles(abs(int(valor)))}"


@register.filter
def sin_detalle(texto):
    """'Contenido audiovisual (4 reels)' -> 'Contenido audiovisual' (nombre corto para cintas y etiquetas)."""
    return re.sub(r"\s*\([^)]*\)", "", str(texto or "")).strip()


@register.filter
def con_iva(valor):
    """150000 -> 178500 (precio neto del catálogo -> precio final con IVA incluido). Usar antes de |clp."""
    from apps.core.impuestos import con_iva as _con_iva

    return _con_iva(valor)
