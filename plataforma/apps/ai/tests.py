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


class RespaldoProveedoresTests(TestCase):
    """Si Gemini se queda sin cuota, se usa el siguiente proveedor gratuito con clave."""

    def _ok_openai(self, texto="Texto de Groq"):
        respuesta = mock.MagicMock()
        respuesta.read.return_value = json.dumps({"choices": [{"message": {"content": texto}}], "usage": {"prompt_tokens": 3, "completion_tokens": 4}, "model": "llama"}).encode()
        respuesta.__enter__.return_value = respuesta
        return respuesta

    @override_settings(AI_API_KEY="g", GROQ_API_KEY="q", OPENROUTER_API_KEY="", AI_PROVEEDORES=["gemini", "groq", "openrouter"])
    def test_si_gemini_agota_la_cuota_responde_groq(self):
        from .services import _llamar_modelo

        with mock.patch("urllib.request.urlopen", side_effect=[_error_http(429, "quota"), self._ok_openai()]):
            texto, entrada, salida, proveedor, modelo = _llamar_modelo("i", "p")
        self.assertEqual((texto, proveedor, entrada, salida), ("Texto de Groq", "groq", 3, 4))

    @override_settings(AI_API_KEY="", GROQ_API_KEY="", OPENROUTER_API_KEY="r", AI_PROVEEDORES=["gemini", "groq", "openrouter"])
    def test_solo_con_openrouter(self):
        from .services import _llamar_modelo

        with mock.patch("urllib.request.urlopen", side_effect=[self._ok_openai("Desde OpenRouter")]) as llamada:
            self.assertEqual(_llamar_modelo("i", "p")[3], "openrouter")
        self.assertIn("openrouter.ai", llamada.call_args.args[0].full_url)

    @override_settings(AI_API_KEY="g", GROQ_API_KEY="q", OPENROUTER_API_KEY="", AI_PROVEEDORES=["gemini", "groq"])
    @mock.patch("apps.ai.services.time.sleep")
    def test_si_todos_fallan_informa_cada_uno(self, _):
        from .services import ErrorIA, _llamar_modelo

        with mock.patch("urllib.request.urlopen", side_effect=[_error_http(429, "quota"), _error_http(429, "rate")]):
            with self.assertRaises(ErrorIA) as ctx:
                _llamar_modelo("i", "p")
        self.assertIn("Gemini", str(ctx.exception))
        self.assertIn("Groq", str(ctx.exception))

    @override_settings(AI_API_KEY="", GROQ_API_KEY="", OPENROUTER_API_KEY="")
    def test_sin_claves_no_configurada(self):
        from .services import IANoConfigurada, _llamar_modelo

        with self.assertRaises(IANoConfigurada):
            _llamar_modelo("i", "p")
