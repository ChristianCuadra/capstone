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


class ContenidoCMSTests(TestCase):
    """CP-005 a CP-008 del Plan de Pruebas (PC-WEB-02)."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        from apps.accounts.models import Rol

        User = get_user_model()
        self.admin = User.objects.create_user(
            "admin_cms", "admin_cms@agenciacosmopolitan.cl", "x", is_staff=True, rol=Rol.ADMINISTRADORA,
        )

    def test_cp005_borrador_no_visible_y_publicado_si(self):
        """Crear una entrada, guardarla como borrador y luego publicarla."""
        from .models import Contenido

        contenido = Contenido.objects.create(titulo="Nueva alianza", cuerpo="Texto de la novedad.", estado=Contenido.Estado.BORRADOR)
        self.assertIsNone(contenido.publicado_en)

        respuesta = self.client.get(reverse("website:novedades"))
        self.assertNotContains(respuesta, "Nueva alianza")
        self.assertEqual(self.client.get(reverse("website:novedad_detalle", args=[contenido.slug])).status_code, 404)

        contenido.estado = Contenido.Estado.PUBLICADO
        contenido.save()
        self.assertIsNotNone(contenido.publicado_en)

        respuesta = self.client.get(reverse("website:novedades"))
        self.assertContains(respuesta, "Nueva alianza")
        self.assertEqual(self.client.get(reverse("website:novedad_detalle", args=[contenido.slug])).status_code, 200)

    def test_cp006_edicion_y_despublicacion(self):
        from .models import Contenido

        contenido = Contenido.objects.create(titulo="Original", cuerpo="Texto", estado=Contenido.Estado.PUBLICADO)
        self.client.force_login(self.admin)

        self.client.post(
            reverse("crm:contenido_editar", args=[contenido.pk]),
            {"titulo": "Editado", "seccion": "novedades", "cuerpo": "Texto editado", "estado": "publicado", "orden": 0},
        )
        contenido.refresh_from_db()
        self.assertEqual(contenido.titulo, "Editado")
        self.assertContains(self.client.get(reverse("website:novedades")), "Editado")

        self.client.post(reverse("crm:contenido_alternar_publicado", args=[contenido.pk]))
        contenido.refresh_from_db()
        self.assertEqual(contenido.estado, Contenido.Estado.BORRADOR)
        self.assertEqual(self.client.get(reverse("website:novedad_detalle", args=[contenido.slug])).status_code, 404)

    def test_cp007_cms_sin_sesion_redirige_a_login(self):
        respuesta = self.client.get(reverse("crm:contenidos"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("account_login"), respuesta.url)
        self.assertNotContains(respuesta, "Contenido del sitio", status_code=302)

    def test_cp008_sanitiza_html_y_scripts(self):
        from .models import Contenido

        contenido = Contenido.objects.create(
            titulo="<script>alert(1)</script>Aviso",
            cuerpo="Texto <b>malicioso</b> con <script>alert('x')</script> incrustado.",
            estado=Contenido.Estado.PUBLICADO,
        )
        self.assertNotIn("<script>", contenido.titulo)
        self.assertNotIn("<script>", contenido.cuerpo)
        self.assertNotIn("<b>", contenido.cuerpo)

        respuesta = self.client.get(reverse("website:novedad_detalle", args=[contenido.slug]))
        self.assertNotContains(respuesta, "<script>alert")


class MensajesSitioPublicoTests(TestCase):
    """Bug reportado por Felipe: el mensaje de 'cerrado sesión' quedaba pegado hasta
    la próxima vez que se abría el login, porque el sitio público no mostraba
    los mensajes de Django (solo el panel interno y las páginas de cuenta lo hacían)."""

    def test_mensaje_de_logout_se_muestra_de_inmediato_en_el_sitio(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        User.objects.create_user("proba", "proba@x.cl", "Mine1234@", is_active=True)
        self.client.login(username="proba", password="Mine1234@")

        respuesta = self.client.post(reverse("account_logout"), follow=True)
        self.assertContains(respuesta, "Ha cerrado sesión")

        # Al volver a visitar el sitio, el mensaje ya no debe reaparecer.
        respuesta2 = self.client.get(reverse("website:home"))
        self.assertNotContains(respuesta2, "Ha cerrado sesión")


class AsesoriaGratuitaHomeTests(TestCase):
    def test_home_destaca_la_asesoria_gratuita_con_boton(self):
        respuesta = self.client.get(reverse("website:home"))
        self.assertContains(respuesta, "Asesoría gratuita")
        self.assertContains(respuesta, 'id="asesoria-mas-info"')
