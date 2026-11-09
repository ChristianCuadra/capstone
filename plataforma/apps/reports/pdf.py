"""PDF del reporte mensual (PC-REP-01) con fpdf2, que es Python puro y funciona en Vercel (sin librerías del sistema)."""

from fpdf import FPDF

VINO = (82, 33, 54)
ROSA = (225, 139, 166)
GRIS = (90, 90, 99)

_REEMPLAZOS = {
    "–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
    "•": "-", "…": "...", " ": " ", "→": "->",
}


def _texto(valor):
    """Las fuentes base del PDF usan Latin-1 (tildes y ñ incluidas); el resto se reemplaza."""
    texto = str(valor if valor is not None else "")
    for origen, destino in _REEMPLAZOS.items():
        texto = texto.replace(origen, destino)
    return texto.encode("latin-1", "replace").decode("latin-1")


def _numero(valor, tipo):
    if valor is None:
        return "-"
    if tipo == "porcentaje":
        return f"{valor} %".replace(".", ",")
    texto = f"{valor:,.0f}".replace(",", ".")
    return f"${texto}" if tipo == "pesos" else texto


def generar_pdf(reporte, agencia_nombre, mes_texto, resumen, cumplimiento):
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_title(_texto(f"Reporte {mes_texto} - {reporte.cliente.nombre}"))
    pdf.set_author(_texto(agencia_nombre))
    pdf.add_page()

    pdf.set_fill_color(*VINO)
    pdf.rect(0, 0, 210, 30, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(15, 9)
    pdf.cell(0, 8, _texto(agencia_nombre))
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(15, 17)
    pdf.cell(0, 6, _texto(f"Reporte mensual · {reporte.cliente.nombre} · {mes_texto}"))

    pdf.set_text_color(*VINO)
    pdf.set_xy(15, 38)

    if resumen.get("hay_datos"):
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Indicadores del mes", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for i in resumen["indicadores"]:
            pdf.set_text_color(*GRIS)
            pdf.cell(90, 7, _texto(i["nombre"]), border="B")
            pdf.set_text_color(*VINO)
            pdf.cell(0, 7, _texto(_numero(i["valor"], i["tipo"])), border="B", align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    if cumplimiento and cumplimiento.get("filas"):
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Cumplimiento del plan", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(245, 238, 242)
        for titulo, ancho in (("Entregable", 70), ("Comprometido", 37), ("Entregado", 37), ("Aprobado", 36)):
            pdf.cell(ancho, 7, titulo, fill=True, align="L" if ancho == 70 else "R")
        pdf.ln()
        pdf.set_font("Helvetica", "", 10)
        for f in cumplimiento["filas"]:
            pdf.cell(70, 7, _texto(f["tipo"]), border="B")
            pdf.cell(37, 7, str(f["comprometido"]), border="B", align="R")
            pdf.cell(37, 7, str(f["entregado"]), border="B", align="R")
            pdf.cell(36, 7, str(f["aprobado"]), border="B", align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _texto("Análisis de la agencia"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(40, 40, 46)
    for linea in reporte.contenido.splitlines():
        es_titulo = linea[:2].strip().rstrip(".").isdigit() and len(linea) < 80
        if es_titulo:
            pdf.ln(1)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*VINO)
        pdf.multi_cell(0, 5.5, _texto(linea) or " ", new_x="LMARGIN", new_y="NEXT")
        if es_titulo:
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(40, 40, 46)

    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*GRIS)
    aprobado = f"Aprobado por la agencia el {reporte.fecha_aprobacion:%d-%m-%Y}." if reporte.fecha_aprobacion else ""
    pdf.multi_cell(0, 4.5, _texto(f"{aprobado} Las cifras provienen de las métricas cargadas en la plataforma y del calendario editorial."))
    return bytes(pdf.output())
