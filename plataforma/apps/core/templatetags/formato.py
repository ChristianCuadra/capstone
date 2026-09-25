"""Filtros de formato chileno: los montos viajan como enteros y se formatean solo al mostrarse."""

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
