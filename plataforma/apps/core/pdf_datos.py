"""PDF legible de los datos personales de una persona o empresa (derecho de acceso, Ley 21.719).

Recibe el mismo diccionario que se entrega en JSON (portabilidad), así ambos formatos muestran lo mismo.
Usa fpdf2, Python puro (funciona en Vercel).
"""

import re
from datetime import datetime

from django.utils import timezone
from fpdf import FPDF

from apps.reports.pdf import VINO, GRIS, _texto


_FECHA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}.*)?$")


def _etiqueta(clave):
    texto = str(clave).replace("_", " ")
    return texto[:1].upper() + texto[1:]


def _fecha(texto):
    """2026-11-09T21:25:50+00:00 -> 09-11-2026 18:25 (hora de Chile); 2026-11-09 -> 09-11-2026."""
    try:
        valor = datetime.fromisoformat(texto)
    except ValueError:
        return texto
    if "T" not in texto:
        return valor.strftime("%d-%m-%Y")
    if timezone.is_aware(valor):
        valor = timezone.localtime(valor)
    return valor.strftime("%d-%m-%Y %H:%M")


def _valor(valor):
    if valor in (None, "", [], {}):
        return "-"
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, list) and all(not isinstance(v, (dict, list)) for v in valor):
        return ", ".join(str(v) for v in valor)
    if isinstance(valor, str) and _FECHA_ISO.match(valor):
        return _fecha(valor)
    return str(valor)


def generar_pdf_datos(titulo, datos):
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_title(_texto(titulo))
    pdf.add_page()
    pdf.set_fill_color(*VINO)
    pdf.rect(0, 0, 210, 26, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_xy(15, 8)
    pdf.cell(0, 7, _texto(titulo))
    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(15, 15)
    pdf.cell(0, 6, _texto(f"Responsable: {datos.get('responsable', '')} · Generado el {_fecha(str(datos.get('generado_en', '')))}"))
    pdf.set_xy(15, 32)
    pdf.set_text_color(40, 40, 46)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 4.5, _texto(
        "Este documento reúne los datos personales que la plataforma guarda, en respuesta a una solicitud de acceso "
        "(Ley 21.719). La misma información se entrega en formato JSON para portabilidad."
    ), new_x="LMARGIN", new_y="NEXT")

    for clave, valor in datos.items():
        if clave in ("responsable", "generado_en"):
            continue
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*VINO)
        pdf.cell(0, 7, _texto(_etiqueta(clave)), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 46)
        if isinstance(valor, dict):
            _tabla(pdf, valor.items())
        elif isinstance(valor, list) and valor and isinstance(valor[0], dict):
            for i, elemento in enumerate(valor, start=1):
                pdf.set_text_color(*GRIS)
                pdf.cell(0, 5, _texto(f"{_etiqueta(clave)} {i}"), new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(40, 40, 46)
                _tabla(pdf, elemento.items())
                pdf.ln(1)
        else:
            pdf.multi_cell(0, 5, _texto(_valor(valor)), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _tabla(pdf, pares):
    for etiqueta, valor in pares:
        x = pdf.get_x()
        y = pdf.get_y()
        pdf.set_text_color(*GRIS)
        pdf.multi_cell(55, 5, _texto(_etiqueta(etiqueta)), border="B", new_x="RIGHT", new_y="TOP")
        alto_etiqueta = pdf.get_y() - y
        pdf.set_xy(x + 55, y)
        pdf.set_text_color(40, 40, 46)
        pdf.multi_cell(0, 5, _texto(_valor(valor)), border="B", new_x="LMARGIN", new_y="NEXT")
        if pdf.get_y() < y + alto_etiqueta:
            pdf.set_y(y + alto_etiqueta)
