"""IVA de Chile en un solo lugar.

El catálogo (planes y servicios) guarda el precio NETO, y el sitio público lo muestra neto («+ IVA»).
La cotización desglosa neto + IVA = total, y el panel muestra el total con IVA como referencia.
"""

TASA_IVA = 0.19


def iva_de(neto):
    """IVA de un monto neto en pesos (redondeado al peso)."""
    return round(int(neto) * TASA_IVA)


def con_iva(neto):
    """Precio final con IVA incluido. None se mantiene None (p. ej. un plan sin precio de primer mes)."""
    if neto in (None, ""):
        return None
    return int(neto) + iva_de(neto)
