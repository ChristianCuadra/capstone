"""Proveedores de IA con respaldo entre ellos (planes gratuitos).

Orden según AI_PROVEEDORES (por defecto gemini, groq, openrouter). Solo participan los que tienen clave.
Si uno falla por cuota agotada (429), saturación (5xx), demora, sin conexión o clave inválida, se intenta
con el siguiente; si todos fallan, se informa el error de cada uno. Así una cuota diaria agotada (o un cobro
que obligue a desactivar una clave) no deja a la agencia sin IA.

- Gemini (Google AI Studio): gratuito mientras el proyecto de la clave NO tenga facturación vinculada.
- Groq: plan gratuito sin tarjeta, API compatible con OpenAI.
- OpenRouter: modelos «:free» o el enrutador «openrouter/free», gratuitos con límite de solicitudes por día.
"""

import json
import urllib.error
import urllib.request

from django.conf import settings

OPENAI_COMPATIBLES = {
    "groq": {"nombre": "Groq", "url": "https://api.groq.com/openai/v1/chat/completions", "clave": "GROQ_API_KEY", "modelo": "GROQ_MODEL"},
    "openrouter": {"nombre": "OpenRouter", "url": "https://openrouter.ai/api/v1/chat/completions", "clave": "OPENROUTER_API_KEY", "modelo": "OPENROUTER_MODEL"},
}
NOMBRES = {"gemini": "Gemini", **{k: v["nombre"] for k, v in OPENAI_COMPATIBLES.items()}}


def clave_de(proveedor):
    if proveedor == "gemini":
        return settings.AI_API_KEY
    datos = OPENAI_COMPATIBLES.get(proveedor)
    return getattr(settings, datos["clave"], "") if datos else ""


def proveedores_activos():
    return [p for p in getattr(settings, "AI_PROVEEDORES", ["gemini"]) if p in NOMBRES and clave_de(p)]


def llamar_openai_compatible(proveedor, instrucciones, prompt):
    """(texto, tokens_entrada, tokens_salida, modelo). Lanza ErrorIA si falla."""
    from .services import ErrorIA

    datos = OPENAI_COMPATIBLES[proveedor]
    nombre = datos["nombre"]
    modelo = getattr(settings, datos["modelo"])
    cuerpo = {
        "model": modelo,
        "messages": [{"role": "system", "content": instrucciones}, {"role": "user", "content": prompt}],
        "temperature": 0.6,
        "max_tokens": 2048,
    }
    cabeceras = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {clave_de(proveedor)}",
        "User-Agent": "Mozilla/5.0 (compatible; PlataformaCosmopolitan/1.0)",
    }
    if proveedor == "openrouter":
        cabeceras["X-Title"] = "Plataforma Cosmopolitan"
    peticion = urllib.request.Request(datos["url"], data=json.dumps(cuerpo).encode(), headers=cabeceras, method="POST")
    try:
        with urllib.request.urlopen(peticion, timeout=15) as respuesta:
            datos_respuesta = json.loads(respuesta.read())
    except urllib.error.HTTPError as e:
        detalle = f"{nombre} respondió {e.code}: {e.read().decode(errors='replace')[:500]}"
        mensajes = {
            401: f"La clave de {nombre} no es válida.",
            402: f"{nombre} pide saldo para este modelo.",
            403: f"La clave de {nombre} no tiene acceso.",
            404: f"El modelo configurado en {nombre} no está disponible.",
            429: f"Se alcanzó el límite gratuito de {nombre}.",
        }
        raise ErrorIA(mensajes.get(e.code, f"{nombre} no está respondiendo."), detalle) from e
    except TimeoutError as e:
        raise ErrorIA(f"{nombre} tardó demasiado en responder.", f"Sin respuesta de {nombre} en 15 s: {e}") from e
    except urllib.error.URLError as e:
        raise ErrorIA(f"No se pudo conectar con {nombre}.", f"No se pudo conectar con {nombre}: {e.reason}") from e

    opciones = datos_respuesta.get("choices") or [{}]
    texto = ((opciones[0].get("message") or {}).get("content") or "").strip()
    if not texto:
        raise ErrorIA(f"{nombre} no devolvió texto.", f"{nombre} sin texto: {str(datos_respuesta)[:300]}")
    uso = datos_respuesta.get("usage") or {}
    return texto, uso.get("prompt_tokens"), uso.get("completion_tokens"), datos_respuesta.get("model") or modelo