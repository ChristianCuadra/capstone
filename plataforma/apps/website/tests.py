from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Plan, Servicio
from apps.crm.models import Prospecto

DATOS_VALIDOS = {
    "nombre": "Ana Pérez",
    "empresa": "Café Prueba",
    "correo": "ana@cafeprueba.cl",
    "rubro": "Gastronomía y cafeterías",
    "region": "Metropolitana de Santiago",
    "tamano": "2_10",
    "agencia_actual": "no",
    "presupuesto": "150_250",
    "objetivos": ["Vender más online", "Aumentar seguidores"],
    "redes_actuales": ["instagram"],
    "instagram": "@cafeprueba",
    "como_nos_conocio": "instagram",
    "situacion_actual": "Publicamos poco.",
    "acepta_privacidad": "on",
}


class SitioPublicoTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_sitemap_responde(self):
        respuesta = self.client.get("/sitemap.xml")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/xml")
        for nombre in (reverse("website:home"), reverse("website:planes"), reverse("website:cotizacion")):
            self.assertContains(respuesta, nombre)

    def test_meta_descripcion_por_pagina(self):
        for nombre in ("website:home", "website:planes", "website:cotizacion"):
            with self.subTest(nombre=nombre):
                respuesta = self.client.get(reverse(nombre))
                self.assertContains(respuesta, '<meta name="description"')

    def test_paginas_responden(self):
        for nombre in ("website:home", "website:planes", "website:cotizacion"):
            with self.subTest(nombre=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 200)

    def test_home_sin_datos_inventados(self):
        respuesta = self.client.get(reverse("website:home"))
        for texto in ("Café Kütral", "Óptica Lumen", "18</dd>", "4,2x"):
            self.assertNotContains(respuesta, texto)
        self.assertContains(respuesta, "Pía Mercado")  # sección Nosotras, según el Documento de Alcance
        self.assertNotContains(respuesta, 'href="https://instagram.com/agenciacosmopolitan"')

    def test_planes_vienen_del_catalogo(self):
        respuesta = self.client.get(reverse("website:planes"))
        nombres = [p["nombre"] for p in respuesta.context["planes"]]
        self.assertEqual(nombres, ["Presencia", "Posicionamiento", "Crecimiento", "Expansión"])
        self.assertContains(respuesta, "Primer mes $400.000")

    def test_plan_oculto_no_aparece_en_el_sitio(self):
        Plan.objects.filter(slug="expansion").update(visible_en_sitio=False)
        nombres = [p["nombre"] for p in self.client.get(reverse("website:planes")).context["planes"]]
        self.assertNotIn("Expansión", nombres)


class FormularioCotizacionTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_solicitud_crea_prospecto_con_plan_sugerido(self):
        datos = {**DATOS_VALIDOS, "servicios_requeridos": [Servicio.objects.get(slug="publicidad-ads").pk], "plan": "crecimiento"}
        respuesta = self.client.post(reverse("website:cotizacion"), datos)
        self.assertRedirects(respuesta, reverse("website:cotizacion") + "?enviado=1")

        p = Prospecto.objects.get()
        self.assertEqual(p.empresa, "Café Prueba")
        self.assertEqual(p.instagram, "cafeprueba")  # sin @
        self.assertEqual(p.plan_interes.slug, "crecimiento")
        # Ads + reels caben en Posicionamiento ($200.000), dentro del presupuesto 150–250.
        self.assertEqual(p.plan_sugerido.slug, "posicionamiento")
        self.assertEqual(p.interacciones.count(), 1)

        confirmacion = self.client.get(reverse("website:cotizacion") + "?enviado=1")
        self.assertContains(confirmacion, "Posicionamiento")

    def test_campos_obligatorios(self):
        respuesta = self.client.post(reverse("website:cotizacion"), {"nombre": "Ana"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Revisa los campos marcados")
        self.assertFalse(Prospecto.objects.exists())

    def test_campo_trampa_no_guarda(self):
        respuesta = self.client.post(reverse("website:cotizacion"), {**DATOS_VALIDOS, "sitio_empresa": "http://spam"})
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(Prospecto.objects.exists())

    def test_limite_de_envios_por_hora(self):
        for _ in range(5):
            self.client.post(reverse("website:cotizacion"), DATOS_VALIDOS)
        respuesta = self.client.post(reverse("website:cotizacion"), DATOS_VALIDOS)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Prospecto.objects.count(), 5)


class CuentasTests(TestCase):
    def test_registro_publico_cerrado(self):
        respuesta = self.client.get(reverse("account_signup"))
        self.assertNotContains(respuesta, 'name="password1"')
