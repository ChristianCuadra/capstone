"""Cliente de Gemini: reintentos ante saturación y mensajes claros para el equipo (PC-IA-01, criterio 3)."""

import io
import json
import urllib.error
from unittest import mock

from django.test import TestCase, override_settings

from .models import RegistroIA
from .services import ErrorIA, reescribir_texto


def _error_http(codigo, mensaje="error"):
    cuerpo = io.BytesIO(json.dumps({"error": {"code": codigo, "message": mensaje}}).encode())
    return urllib.error.HTTPError("https://gemini", codigo, mensaje, {}, cuerpo)


def _respuesta_ok(texto="Texto reescrito"):
    respuesta = mock.MagicMock()
    respuesta.read.return_value = json.dumps({
        "candidates": [{"content": {"parts": [{"text": texto}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }).encode()
    respuesta.__enter__.return_value = respuesta
    return respuesta


@override_settings(AI_API_KEY="clave-de-prueba", AI_MODEL="modelo-de-prueba")
@mock.patch("apps.ai.services.time.sleep")
class ClienteGeminiTests(TestCase):
    def test_reintenta_si_gemini_esta_saturado_y_luego_responde(self, _sleep):
        with mock.patch("urllib.request.urlopen", side_effect=[_error_http(503, "high demand"), _respuesta_ok()]) as llamada:
            texto = reescribir_texto("Borrador", "Acórtalo", None)
        self.assertEqual(texto, "Texto reescrito")
        self.assertEqual(llamada.call_count, 2)
        self.assertTrue(RegistroIA.objects.get().exitoso)

    def test_si_sigue_saturado_avisa_en_espanol_y_registra_el_detalle(self, _sleep):
        with mock.patch("urllib.request.urlopen", side_effect=[_error_http(503, "high demand") for _ in range(3)]) as llamada:
            with self.assertRaises(ErrorIA) as error:
                reescribir_texto("Borrador", "Acórtalo", None)
        self.assertEqual(llamada.call_count, 3)
        self.assertIn("alta demanda", str(error.exception))
        self.assertNotIn("{", str(error.exception))  # nada de JSON del proveedor en el panel
        registro = RegistroIA.objects.get()
        self.assertFalse(registro.exitoso)
        self.assertIn("503", registro.error)
        self.assertIn("high demand", registro.error)

    def test_clave_sin_acceso_no_se_reintenta(self, _sleep):
        with mock.patch("urllib.request.urlopen", side_effect=[_error_http(403, "denied")]) as llamada:
            with self.assertRaises(ErrorIA) as error:
                reescribir_texto("Borrador", "Acórtalo", None)
        self.assertEqual(llamada.call_count, 1)
        self.assertIn("AI_API_KEY", str(error.exception))

    def test_cuota_diaria_agotada_no_se_reintenta_y_dice_cuando_se_renueva(self, _sleep):
        aviso = "Quota exceeded for metric: generate_content_free_tier_requests, limit: 20. Please retry in 23h2m47s."
        with mock.patch("urllib.request.urlopen", side_effect=[_error_http(429, aviso)]) as llamada:
            with self.assertRaises(ErrorIA) as error:
                reescribir_texto("Borrador", "Acórtalo", None)
        self.assertEqual(llamada.call_count, 1)  # reintentar solo gastaría más cuota
        self.assertIn("cuota diaria", str(error.exception))
        self.assertIn("24 horas", str(error.exception))
        self.assertIn("modelo-de-prueba", str(error.exception))

    def test_demora_excesiva_se_informa(self, _sleep):
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaises(ErrorIA) as error:
                reescribir_texto("Borrador", "Acórtalo", None)
        self.assertIn("tardó demasiado", str(error.exception))
        self.assertIn("60 s", RegistroIA.objects.get().error)
