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
        # El catálogo guarda el neto ($400.000); el sitio muestra el precio final con IVA incluido.
        self.assertContains(respuesta, "Primer mes $476.000")
        self.assertContains(respuesta, "$178.500")  # Presencia: $150.000 + IVA
        self.assertNotContains(respuesta, "$150.000<span")
        self.assertContains(respuesta, "IVA incluido")

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
        for i in range(5):
            self.client.post(reverse("website:cotizacion"), {**DATOS_VALIDOS, "correo": f"ana{i}@cafeprueba.cl"})
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


class PreciosConIvaTests(TestCase):
    """Decisión del 11 oct 2026: el sitio muestra precios con IVA incluido; el catálogo guarda el neto."""

    def test_home_muestra_servicios_y_plan_desde_con_iva(self):
        respuesta = self.client.get(reverse("website:home"))
        self.assertContains(respuesta, "desde $178.500 al mes")
        self.assertContains(respuesta, "$41.650")  # Asesorías: $35.000 + IVA
        self.assertContains(respuesta, "IVA incluido")

    def test_filtro_con_iva_redondea_al_peso(self):
        from apps.core.impuestos import con_iva, iva_de

        self.assertEqual(con_iva(150000), 178500)
        self.assertEqual(iva_de(33333), 6333)
        self.assertIsNone(con_iva(None))

    def test_cotizacion_usa_el_mismo_calculo(self):
        from apps.core.impuestos import TASA_IVA
        from apps.crm.models import Cotizacion

        self.assertEqual(Cotizacion.IVA, TASA_IVA)

    def test_panel_muestra_neto_y_con_iva(self):
        from django.contrib.auth import get_user_model

        admin = get_user_model().objects.create_user("adm_iva", "adm_iva@x.cl", "x", is_staff=True, rol="administradora")
        self.client.force_login(admin)
        respuesta = self.client.get(reverse("crm:planes_servicios"))
        self.assertContains(respuesta, "$150.000")
        self.assertContains(respuesta, "$178.500 con IVA")


DATOS_ASESORIA = {
    "nombre": "Bea Soto",
    "empresa": "Tienda Bea",
    "correo": "Bea@TiendaBea.cl",
    "telefono": "+56 9 1111 2222",
    "rubro": "Retail y moda",
    "region": "Valparaíso",
    "tamano": "solo",
    "instagram": "@tiendabea",
    "situacion_actual": "Vendemos poco por Instagram y no sabemos qué publicar.",
    "acepta_privacidad": "on",
}


class AsesoriaGratuitaTests(TestCase):
    """Botón «Más información» del inicio: el visitante cuenta su caso y se envía por correo a la agencia."""

    def setUp(self):
        cache.clear()

    def test_boton_del_inicio_lleva_a_la_asesoria(self):
        respuesta = self.client.get(reverse("website:home"))
        self.assertContains(respuesta, f'href="{reverse("website:asesoria")}" id="asesoria-mas-info"')

    def test_pagina_muestra_contacto_por_correo_y_whatsapp(self):
        respuesta = self.client.get(reverse("website:asesoria"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "mailto:hola@agenciacosmopolitan.cl")
        self.assertContains(respuesta, "https://wa.me/56987654321")
        self.assertContains(respuesta, '<meta name="description"')

    def test_envio_guarda_prospecto_y_manda_correo_a_la_agencia(self):
        from django.core import mail

        respuesta = self.client.post(reverse("website:asesoria"), DATOS_ASESORIA)
        self.assertRedirects(respuesta, reverse("website:asesoria") + "?enviado=1")

        p = Prospecto.objects.get()
        self.assertEqual(p.canal, Prospecto.Canal.ASESORIA)
        self.assertEqual(p.correo, "bea@tiendabea.cl")
        self.assertEqual(p.instagram, "tiendabea")
        self.assertIn("Vendemos poco", p.situacion_actual)
        self.assertEqual(p.interacciones.count(), 1)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["hola@agenciacosmopolitan.cl"])
        self.assertIn("Tienda Bea", mail.outbox[0].subject)
        self.assertIn("Vendemos poco", mail.outbox[0].body)
        self.assertIn(reverse("crm:prospecto_detalle", args=[p.pk]), mail.outbox[0].body)

        confirmacion = self.client.get(reverse("website:asesoria") + "?enviado=1")
        self.assertContains(confirmacion, "Recibimos tu caso")

    def test_el_caso_es_obligatorio(self):
        respuesta = self.client.post(reverse("website:asesoria"), {**DATOS_ASESORIA, "situacion_actual": ""})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Cuéntanos tu caso")
        self.assertFalse(Prospecto.objects.exists())

    def test_campo_trampa_no_guarda_ni_envia(self):
        from django.core import mail

        respuesta = self.client.post(reverse("website:asesoria"), {**DATOS_ASESORIA, "sitio_empresa": "spam"})
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(Prospecto.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_si_falla_el_correo_el_caso_igual_queda_guardado(self):
        from unittest import mock

        with mock.patch("apps.crm.services.send_mail", side_effect=OSError("sin servidor de correo")):
            respuesta = self.client.post(reverse("website:asesoria"), DATOS_ASESORIA)
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(Prospecto.objects.filter(canal=Prospecto.Canal.ASESORIA).exists())

    def test_cotizacion_despues_de_la_asesoria_precarga_y_no_duplica(self):
        self.client.post(reverse("website:asesoria"), DATOS_ASESORIA)
        asesoria = Prospecto.objects.get()

        formulario = self.client.get(reverse("website:cotizacion"))
        self.assertContains(formulario, 'value="Tienda Bea"')
        self.assertContains(formulario, 'value="bea@tiendabea.cl"')

        datos = {**DATOS_VALIDOS, "nombre": "Bea Soto", "empresa": "Tienda Bea", "correo": "bea@tiendabea.cl"}
        self.client.post(reverse("website:cotizacion"), datos)

        self.assertEqual(Prospecto.objects.count(), 1)
        p = Prospecto.objects.get()
        self.assertEqual(p.pk, asesoria.pk)
        self.assertEqual(p.canal, Prospecto.Canal.ASESORIA)  # se conserva por dónde llegó primero
        self.assertEqual(p.presupuesto, "150_250")  # ahora con los datos de la cotización
        self.assertIsNotNone(p.plan_sugerido)
        self.assertEqual(p.interacciones.count(), 2)

    def test_cliente_ya_convertido_no_se_reutiliza(self):
        from apps.clients.models import Cliente

        self.client.post(reverse("website:asesoria"), DATOS_ASESORIA)
        p = Prospecto.objects.get()
        p.cliente = Cliente.objects.create(nombre="Tienda Bea")
        p.etapa = Prospecto.Etapa.GANADO
        p.save()
        self.client.post(reverse("website:asesoria"), DATOS_ASESORIA)
        self.assertEqual(Prospecto.objects.count(), 2)

    def test_sitemap_incluye_la_asesoria(self):
        self.assertContains(self.client.get("/sitemap.xml"), reverse("website:asesoria"))


class OrigenVisitaTests(TestCase):
    """PC-CAP-01: el prospecto se crea con su origen (UTM o sitio de referencia)."""

    def setUp(self):
        cache.clear()

    def test_campana_utm_queda_en_el_prospecto(self):
        self.client.get("/planes/?utm_source=instagram&utm_medium=paid&utm_campaign=octubre")
        self.client.get(reverse("website:cotizacion"))  # navegación interna: no borra la campaña
        self.client.post(reverse("website:cotizacion"), DATOS_VALIDOS)
        p = Prospecto.objects.get()
        self.assertEqual((p.utm_source, p.utm_medium, p.utm_campaign), ("instagram", "paid", "octubre"))
        self.assertTrue(p.pagina_entrada.startswith("/planes/?utm_source=instagram"))

    def test_referencia_externa_sin_utm(self):
        self.client.get("/", HTTP_REFERER="https://www.google.com/search?q=agencia")
        self.client.post(reverse("website:asesoria"), DATOS_ASESORIA)
        p = Prospecto.objects.get()
        self.assertEqual(p.utm_source, "")
        self.assertEqual(p.sitio_referencia, "https://www.google.com/search?q=agencia")
        self.assertEqual(p.pagina_entrada, "/")

    def test_visita_directa_no_guarda_origen_ni_crea_sesion(self):
        respuesta = self.client.get("/")
        self.assertNotIn("sessionid", respuesta.cookies)
        self.client.post(reverse("website:cotizacion"), DATOS_VALIDOS)
        self.assertFalse(Prospecto.objects.get().tiene_origen)

    def test_link_sin_campana_no_reemplaza_una_campana(self):
        self.client.get("/?utm_source=newsletter&utm_campaign=lanzamiento")
        self.client.get("/planes/", HTTP_REFERER="https://www.facebook.com/")
        self.client.post(reverse("website:cotizacion"), DATOS_VALIDOS)
        self.assertEqual(Prospecto.objects.get().utm_campaign, "lanzamiento")

    def test_panel_no_registra_origen(self):
        self.client.get("/panel/?utm_source=x")
        self.assertNotIn("origen_visita", self.client.session)

    def test_ficha_del_prospecto_muestra_el_origen(self):
        from django.contrib.auth import get_user_model

        self.client.get("/?utm_source=instagram&utm_campaign=octubre")
        self.client.post(reverse("website:cotizacion"), DATOS_VALIDOS)
        p = Prospecto.objects.get()
        admin = get_user_model().objects.create_user("adm_utm", "adm_utm@x.cl", "x", is_staff=True, rol="administradora")
        self.client.force_login(admin)
        respuesta = self.client.get(reverse("crm:prospecto_detalle", args=[p.pk]))
        self.assertContains(respuesta, "Origen de la visita")
        self.assertContains(respuesta, "Campaña: octubre")

    def test_ficha_de_asesoria_sin_cotizar_no_inventa_plan(self):
        from django.contrib.auth import get_user_model

        self.client.post(reverse("website:asesoria"), DATOS_ASESORIA)
        p = Prospecto.objects.get()
        admin = get_user_model().objects.create_user("adm_as", "adm_as@x.cl", "x", is_staff=True, rol="administradora")
        self.client.force_login(admin)
        respuesta = self.client.get(reverse("crm:prospecto_detalle", args=[p.pk]))
        self.assertContains(respuesta, "Aún no cotiza")
        self.assertContains(respuesta, "Asesoría gratuita (sitio)")


class MenuNovedadesTests(TestCase):
    def test_sin_entradas_publicadas_no_aparece(self):
        from .models import Contenido

        Contenido.objects.create(titulo="Borrador", cuerpo="x", estado=Contenido.Estado.BORRADOR)
        self.assertNotContains(self.client.get(reverse("website:home")), f'href="{reverse("website:novedades")}"')

    def test_con_una_entrada_publicada_aparece_en_el_menu(self):
        from .models import Contenido

        Contenido.objects.create(titulo="Lanzamiento", cuerpo="x", estado=Contenido.Estado.PUBLICADO)
        respuesta = self.client.get(reverse("website:home"))
        self.assertContains(respuesta, f'href="{reverse("website:novedades")}"', count=2)  # menú escritorio y móvil
