"""Lectura y validación de archivos de métricas (PC-MET-01).

Acepta CSV (separado por coma o punto y coma) y Excel (.xlsx). Reconoce los encabezados de la plantilla
de la plataforma y los nombres más comunes de las exportaciones de Instagram Insights y Meta Ads, en
español o inglés. Si hay cualquier error, no se carga ninguna fila (criterio 2: sin datos parciales).
"""

import csv
import io
import os
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import ImportacionMetricas, MetricaDiaria

TAMANO_MAX_MB = 5
MAX_FILAS = 5000
MAX_ERRORES_MOSTRADOS = 15

CAMPOS_ENTEROS = ["alcance", "impresiones", "interacciones", "seguidores", "clics", "resultados"]
CAMPOS = ["fecha"] + CAMPOS_ENTEROS + ["gasto"]

# Encabezados normalizados (minúsculas, sin tildes ni signos) que se aceptan para cada campo.
ALIAS = {
    "fecha": {"fecha", "dia", "date", "day", "inicio del informe", "reporting starts", "fecha de inicio"},
    "alcance": {"alcance", "reach", "cuentas alcanzadas", "accounts reached"},
    "impresiones": {"impresiones", "impressions", "visualizaciones", "views"},
    "interacciones": {
        "interacciones", "engagement", "post engagement", "interacciones con la publicacion",
        "interacciones totales", "total interactions", "interacciones con el contenido",
    },
    "seguidores": {"seguidores", "followers", "seguidores totales", "total followers"},
    "clics": {
        "clics", "clicks", "clics en el enlace", "link clicks", "clics todos", "clicks all",
        "clics en el sitio web", "website clicks",
    },
    "gasto": {"gasto", "importe gastado", "importe gastado clp", "amount spent", "amount spent clp", "inversion"},
    "resultados": {"resultados", "results", "conversiones", "conversions"},
}

ENCABEZADOS_PLANTILLA = ["Fecha", "Alcance", "Impresiones", "Interacciones", "Seguidores", "Clics", "Importe gastado (CLP)", "Resultados"]


class ErrorArchivo(Exception):
    def __init__(self, errores):
        super().__init__("; ".join(errores))
        self.errores = errores


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", texto)).strip()


def _mapear_encabezados(encabezados):
    mapa, errores = {}, []
    for i, enc in enumerate(encabezados):
        clave = normalizar(enc)
        for campo, alias in ALIAS.items():
            if clave in alias:
                if campo in mapa.values():
                    errores.append(f"La columna «{enc}» está repetida.")
                mapa[i] = campo
                break
    if "fecha" not in mapa.values():
        errores.append("Falta la columna «Fecha». Usa la plantilla o una exportación diaria de Instagram o Meta Ads.")
    if not set(mapa.values()) - {"fecha"}:
        errores.append("No se encontró ninguna columna de métricas (alcance, impresiones, interacciones, seguidores, clics, gasto o resultados).")
    return mapa, errores


def _fecha(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for formato in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%y", "%d/%m/%y"):
        try:
            return datetime.strptime(texto[:10] if formato.startswith("%Y") else texto, formato).date()
        except ValueError:
            continue
    raise ValueError(f"fecha «{texto}» no válida (usa dd-mm-aaaa)")


def _numero(valor, decimal=False):
    """Interpreta 1.234 / 1,234 / 1.234,56 / 1234.56. Vacío = None."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, (int, float, Decimal)) and not isinstance(valor, bool):
        numero = Decimal(str(valor))
    else:
        texto = re.sub(r"[\s$]", "", str(valor)).replace("CLP", "")
        if "," in texto and "." in texto:
            decimal_sep = "," if texto.rfind(",") > texto.rfind(".") else "."
            miles = "." if decimal_sep == "," else ","
            texto = texto.replace(miles, "").replace(decimal_sep, ".")
        elif "," in texto:
            texto = texto.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+", texto) else texto.replace(",", ".")
        elif "." in texto and re.fullmatch(r"-?\d{1,3}(\.\d{3})+", texto):
            texto = texto.replace(".", "")
        try:
            numero = Decimal(texto)
        except InvalidOperation as exc:
            raise ValueError(f"«{valor}» no es un número") from exc
    if numero < 0:
        raise ValueError(f"«{valor}» es negativo")
    if decimal:
        return numero.quantize(Decimal("0.01"))
    if numero != numero.to_integral_value():
        raise ValueError(f"«{valor}» debe ser un número entero")
    return int(numero)


def _leer_filas(archivo):
    nombre = archivo.name.lower()
    extension = os.path.splitext(nombre)[1]
    if extension not in (".csv", ".xlsx"):
        raise ErrorArchivo(["Formato no permitido: sube un archivo .csv o .xlsx."])
    if archivo.size > TAMANO_MAX_MB * 1024 * 1024:
        raise ErrorArchivo([f"El archivo supera los {TAMANO_MAX_MB} MB."])
    contenido = archivo.read()
    if extension == ".xlsx":
        from openpyxl import load_workbook

        try:
            hoja = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True).worksheets[0]
        except Exception as exc:
            raise ErrorArchivo(["No se pudo leer el Excel. Revisa que no esté dañado ni protegido con contraseña."]) from exc
        return [list(fila) for fila in hoja.iter_rows(values_only=True)]
    for codificacion in ("utf-8-sig", "latin-1"):
        try:
            texto = contenido.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    primera = texto.splitlines()[0] if texto.strip() else ""
    separador = ";" if primera.count(";") > primera.count(",") else ","
    return list(csv.reader(io.StringIO(texto), delimiter=separador))


def leer_archivo(archivo):
    """Lista de dicts validados ({'fecha': date, 'alcance': int, ...}). Lanza ErrorArchivo con todos los errores."""
    filas = [f for f in _leer_filas(archivo) if any(str(c).strip() for c in f if c is not None)]
    if not filas:
        raise ErrorArchivo(["El archivo está vacío."])
    mapa, errores = _mapear_encabezados(filas[0])
    if errores:
        raise ErrorArchivo(errores)
    datos = filas[1:]
    if not datos:
        raise ErrorArchivo(["El archivo no tiene filas de datos bajo los encabezados."])
    if len(datos) > MAX_FILAS:
        raise ErrorArchivo([f"El archivo tiene más de {MAX_FILAS} filas. Divídelo en partes."])

    validas, vistas = [], {}
    for n, fila in enumerate(datos, start=2):
        registro = {}
        for i, campo in mapa.items():
            valor = fila[i] if i < len(fila) else None
            try:
                registro[campo] = _fecha(valor) if campo == "fecha" else _numero(valor, decimal=campo == "gasto")
            except ValueError as e:
                errores.append(f"Fila {n}, {campo}: {e}.")
        if "fecha" in registro:
            if registro["fecha"] in vistas:
                errores.append(f"Fila {n}: la fecha {registro['fecha']:%d-%m-%Y} ya aparece en la fila {vistas[registro['fecha']]}.")
            vistas[registro["fecha"]] = n
        validas.append(registro)
    if errores:
        extra = len(errores) - MAX_ERRORES_MOSTRADOS
        raise ErrorArchivo(errores[:MAX_ERRORES_MOSTRADOS] + ([f"… y {extra} errores más."] if extra > 0 else []))
    return validas


@transaction.atomic
def importar(archivo, cliente, fuente, usuario):
    """Valida todo el archivo y, solo si no hay errores, lo carga. Devuelve la ImportacionMetricas."""
    filas = leer_archivo(archivo)
    fechas = [f["fecha"] for f in filas]
    importacion = ImportacionMetricas.all_objects.create(
        cliente=cliente, fuente=fuente, nombre_archivo=archivo.name[:200], filas=len(filas),
        desde=min(fechas), hasta=max(fechas), subido_por=usuario,
    )
    for fila in filas:
        valores = {campo: fila.get(campo) for campo in CAMPOS if campo != "fecha"}
        MetricaDiaria.all_objects.update_or_create(
            cliente=cliente, fecha=fila["fecha"], fuente=fuente, defaults={**valores, "importacion": importacion},
        )
    return importacion


def plantilla_csv():
    """Plantilla para la agencia: encabezados y una fila de ejemplo que se debe reemplazar."""
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow(ENCABEZADOS_PLANTILLA)
    escritor.writerow(["01-11-2026", "1200", "2500", "180", "3450", "40", "15000", "3"])
    return "﻿" + salida.getvalue()
