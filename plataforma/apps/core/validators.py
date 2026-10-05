"""Validadores compartidos (RUT chileno)."""

import re

from django.core.exceptions import ValidationError


def _digito_verificador(cuerpo: str) -> str:
    suma, multiplicador = 0, 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1
    resto = 11 - suma % 11
    return "0" if resto == 11 else "K" if resto == 10 else str(resto)


def formatear_rut(valor: str) -> str:
    """Devuelve el RUT como 12.345.678-5. Lanza ValidationError si no es un RUT válido."""
    limpio = re.sub(r"[.\s-]", "", valor or "").upper()
    if len(limpio) < 2 or not limpio[:-1].isdigit() or not 7 <= len(limpio[:-1]) <= 8:
        raise ValidationError("Ingresa un RUT válido, por ejemplo 12.345.678-5.")
    cuerpo, dv = limpio[:-1], limpio[-1]
    if _digito_verificador(cuerpo) != dv:
        raise ValidationError("El RUT no es válido: revisa el dígito verificador.")
    return f"{int(cuerpo):,}".replace(",", ".") + f"-{dv}"
