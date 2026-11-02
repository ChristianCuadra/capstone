from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Rol


class PortalTests(TestCase):
    def test_exige_login(self):
        respuesta = self.client.get(reverse("content:calendario"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("account_login"), respuesta["Location"])

    def test_paginas_vacias_sin_datos_de_ejemplo(self):
        self.client.force_login(get_user_model().objects.create_user("cliente", "cliente@x.cl", "x", rol=Rol.CLIENTE_LECTOR))
        for nombre in ("content:calendario", "content:aprobacion", "content:metricas"):
            with self.subTest(nombre=nombre):
                respuesta = self.client.get(reverse(nombre))
                self.assertEqual(respuesta.status_code, 200)
                self.assertNotContains(respuesta, "Café Kütral")
                self.assertNotContains(respuesta, "pan amasado")

    def test_navegacion_de_meses(self):
        self.client.force_login(get_user_model().objects.create_user("cliente", "cliente@x.cl", "x", rol=Rol.CLIENTE_LECTOR))
        respuesta = self.client.get(reverse("content:calendario"), {"mes": "2026-01"})
        self.assertEqual(respuesta.context["mes_anterior"], "2025-12")
        self.assertEqual(respuesta.context["mes_siguiente"], "2026-02")

    def test_raiz_del_portal_redirige_al_calendario(self):
        self.assertRedirects(self.client.get("/portal/"), reverse("content:calendario"), target_status_code=302)


class SeguridadPanelCalendarioTests(TestCase):
    """Permisos del calendario interno (PC-CAL-01) y protección de la aprobación (PC-APR-01 / PC-APR-02)."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.clients.models import Cliente
        from apps.content.models import EstadoPieza, PiezaContenido

        User = get_user_model()
        self.EstadoPieza = EstadoPieza
        self.PiezaContenido = PiezaContenido
        self.a = Cliente.objects.create(nombre="Panadería Alfa")
        self.b = Cliente.objects.create(nombre="Clínica Beta")
        self.colab = User.objects.create_user("col", "col@x.cl", "x", rol=Rol.COLABORADORA, is_staff=True)
        self.colab.clientes_asignados.set([self.a])
        self.aprobador_a = User.objects.create_user("apa", "apa@x.cl", "x", rol=Rol.CLIENTE_APROBADOR, cliente=self.a)
        self.lector_a = User.objects.create_user("lea", "lea@x.cl", "x", rol=Rol.CLIENTE_LECTOR, cliente=self.a)
        self.aprobador_b = User.objects.create_user("apb", "apb@x.cl", "x", rol=Rol.CLIENTE_APROBADOR, cliente=self.b)
        fecha = timezone.now() + timedelta(days=3)
        self.en_revision = PiezaContenido.objects.create(
            cliente=self.a, titulo="Pieza en revisión", estado=EstadoPieza.EN_REVISION, fecha_programada=fecha
        )
        self.borrador = PiezaContenido.objects.create(
            cliente=self.a, titulo="Pieza borrador", estado=EstadoPieza.BORRADOR, fecha_programada=fecha
        )
        self.datos = {
            "titulo": "Nueva", "texto": "copy", "red_social": "instagram",
            "fecha_programada": "2026-11-20T10:00", "cliente_id": self.a.pk,
        }

    # --- Usuarios cliente fuera del panel ---------------------------------------------------------

    def test_cliente_no_entra_al_calendario_interno(self):
        self.client.force_login(self.aprobador_a)
        respuesta = self.client.get(reverse("content:interna_calendario"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(respuesta["Location"].startswith("/panel/"))

    def test_cliente_no_puede_crear_piezas(self):
        self.client.force_login(self.lector_a)
        total = self.PiezaContenido.all_objects.count()
        self.client.post(reverse("content:crear_pieza"), {**self.datos, "estado": "borrador"})
        self.assertEqual(self.PiezaContenido.all_objects.count(), total)

    def test_cliente_lector_no_puede_aprobar_editando(self):
        self.client.force_login(self.lector_a)
        self.client.post(
            reverse("content:editar_pieza", args=[self.en_revision.pk]), {**self.datos, "estado": "aprobado"}
        )
        self.en_revision.refresh_from_db()
        self.assertEqual(self.en_revision.estado, self.EstadoPieza.EN_REVISION)
        self.assertEqual(self.en_revision.version, 1)

    # --- Estados permitidos para el equipo ---------------------------------------------------------

    def test_no_se_crea_una_pieza_ya_aprobada(self):
        self.client.force_login(self.colab)
        self.client.post(reverse("content:crear_pieza"), {**self.datos, "estado": "aprobado"})
        self.assertFalse(self.PiezaContenido.all_objects.filter(estado=self.EstadoPieza.APROBADO).exists())

    def test_el_equipo_no_puede_aprobar_por_el_cliente(self):
        self.client.force_login(self.colab)
        self.client.post(
            reverse("content:editar_pieza", args=[self.en_revision.pk]), {**self.datos, "estado": "aprobado"}
        )
        self.en_revision.refresh_from_db()
        self.assertEqual(self.en_revision.estado, self.EstadoPieza.EN_REVISION)
        self.assertIsNone(self.en_revision.aprobado_por)
        self.assertFalse(self.en_revision.historial_versiones.exists())

    def test_el_equipo_puede_pedir_cambios_y_reenviar(self):
        self.client.force_login(self.colab)
        url = reverse("content:editar_pieza", args=[self.en_revision.pk])
        self.client.post(url, {**self.datos, "estado": "rechazado"})
        self.en_revision.refresh_from_db()
        self.assertEqual(self.en_revision.estado, self.EstadoPieza.RECHAZADO)
        self.client.post(url, {**self.datos, "estado": "en_revision"})
        self.en_revision.refresh_from_db()
        self.assertEqual(self.en_revision.estado, self.EstadoPieza.EN_REVISION)
        self.assertEqual(self.en_revision.version, 3)

    def test_colaboradora_no_crea_en_cliente_no_asignado(self):
        self.client.force_login(self.colab)
        respuesta = self.client.post(reverse("content:crear_pieza"), {**self.datos, "cliente_id": self.b.pk, "estado": "borrador"})
        self.assertEqual(respuesta.status_code, 404)
        self.assertFalse(self.PiezaContenido.all_objects.filter(cliente=self.b).exists())

    # --- Historial de versiones (lo usan el panel y el portal) -------------------------------------

    def test_cliente_ve_historial_de_su_pieza_en_revision(self):
        self.client.force_login(self.aprobador_a)
        respuesta = self.client.get(reverse("content:obtener_historial_pieza", args=[self.en_revision.pk]))
        self.assertEqual(respuesta.status_code, 200)

    def test_cliente_no_ve_borradores_internos(self):
        self.client.force_login(self.aprobador_a)
        respuesta = self.client.get(reverse("content:obtener_historial_pieza", args=[self.borrador.pk]))
        self.assertEqual(respuesta.status_code, 404)

    def test_cliente_no_ve_piezas_de_otra_empresa(self):
        self.client.force_login(self.aprobador_b)
        respuesta = self.client.get(reverse("content:obtener_historial_pieza", args=[self.en_revision.pk]))
        self.assertEqual(respuesta.status_code, 404)

    def test_equipo_ve_el_borrador(self):
        self.client.force_login(self.colab)
        respuesta = self.client.get(reverse("content:obtener_historial_pieza", args=[self.borrador.pk]))
        self.assertEqual(respuesta.status_code, 200)


class RevisionCalendarioAprobacionesTests(TestCase):
    """Regresiones de la revisión del calendario editorial y las aprobaciones (PC-CAL-01/02, PC-APR-01/02, PC-POR-01)."""

    setUp = SeguridadPanelCalendarioTests.setUp

    def _evaluar(self, pieza, accion="aprobar", **extra):
        datos = {"pieza_id": pieza.pk, "accion": accion, "version": pieza.version, **extra}
        return self.client.post(reverse("content:aprobacion"), datos)

    def _mes(self, fecha):
        from django.utils import timezone

        local = timezone.localtime(fecha)
        return f"{local.year}-{local.month:02d}"

    # --- El cliente solo evalúa lo que está En revisión --------------------------------------------

    def test_aprobador_no_aprueba_un_borrador(self):
        self.client.force_login(self.aprobador_a)
        respuesta = self._evaluar(self.borrador)
        self.assertEqual(respuesta.status_code, 404)
        self.borrador.refresh_from_db()
        self.assertEqual(self.borrador.estado, self.EstadoPieza.BORRADOR)

    def test_aprobador_no_reabre_una_pieza_aprobada(self):
        self.client.force_login(self.aprobador_a)
        self._evaluar(self.en_revision)
        self.en_revision.refresh_from_db()
        self.assertEqual(self.en_revision.estado, self.EstadoPieza.APROBADO)
        self._evaluar(self.en_revision, accion="rechazar", comentario="mejor no")
        self.en_revision.refresh_from_db()
        self.assertEqual(self.en_revision.estado, self.EstadoPieza.APROBADO)

    def test_no_se_aprueba_una_version_que_el_cliente_no_vio(self):
        version_vista = self.en_revision.version
        self.client.force_login(self.colab)
        self.client.post(
            reverse("content:editar_pieza", args=[self.en_revision.pk]),
            {**self.datos, "titulo": "Cambiada", "estado": "en_revision"},
        )
        self.client.force_login(self.aprobador_a)
        self.client.post(
            reverse("content:aprobacion"), {"pieza_id": self.en_revision.pk, "accion": "aprobar", "version": version_vista}
        )
        self.en_revision.refresh_from_db()
        self.assertEqual(self.en_revision.estado, self.EstadoPieza.EN_REVISION)
        self._evaluar(self.en_revision)
        self.en_revision.refresh_from_db()
        self.assertEqual(self.en_revision.estado, self.EstadoPieza.APROBADO)
        self.assertEqual(self.en_revision.aprobado_por, self.aprobador_a)

    def test_pieza_id_mal_escrito_da_404(self):
        self.client.force_login(self.aprobador_a)
        respuesta = self.client.post(reverse("content:aprobacion"), {"pieza_id": "abc", "accion": "aprobar"})
        self.assertEqual(respuesta.status_code, 404)

    # --- Los borradores son solo internos ----------------------------------------------------------

    def test_portal_no_muestra_borradores(self):
        self.client.force_login(self.lector_a)
        mes = self._mes(self.borrador.fecha_programada)
        for respuesta in (
            self.client.get(reverse("content:aprobacion")),
            self.client.get(reverse("content:calendario"), {"mes": mes}),
            self.client.get(reverse("content:calendario"), {"mes": mes, "vista": "lista"}),
        ):
            self.assertContains(respuesta, "Pieza en revisión")
            self.assertNotContains(respuesta, "Pieza borrador")

    def test_cliente_no_ve_versiones_guardadas_como_borrador(self):
        self.client.force_login(self.colab)
        url = reverse("content:editar_pieza", args=[self.borrador.pk])
        self.client.post(url, {**self.datos, "texto": "copy interno", "estado": "en_revision"})
        self.client.force_login(self.aprobador_a)
        datos = self.client.get(reverse("content:obtener_historial_pieza", args=[self.borrador.pk])).json()
        self.assertEqual(datos["historial"], [])
        self.client.force_login(self.colab)
        datos = self.client.get(reverse("content:obtener_historial_pieza", args=[self.borrador.pk])).json()
        self.assertEqual([v["version"] for v in datos["historial"]], [1])

    # --- Validación de datos del panel -------------------------------------------------------------

    def test_no_acepta_archivos_que_no_son_imagen_o_video(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.colab)
        archivo = SimpleUploadedFile("pagina.html", b"<script>alert(1)</script>", content_type="text/html")
        self.client.post(reverse("content:crear_pieza"), {**self.datos, "estado": "borrador", "archivo": archivo})
        self.assertFalse(self.PiezaContenido.all_objects.filter(titulo="Nueva").exists())

    def test_datos_invalidos_no_dan_error_500(self):
        self.client.force_login(self.colab)
        sin_titulo = {k: v for k, v in self.datos.items() if k != "titulo"}
        for nombre, datos in {
            "sin título": sin_titulo,
            "fecha mal escrita": {**self.datos, "fecha_programada": "mañana"},
            "red inexistente": {**self.datos, "red_social": "myspace"},
        }.items():
            with self.subTest(nombre):
                respuesta = self.client.post(reverse("content:crear_pieza"), {**datos, "estado": "borrador"})
                self.assertRedirects(respuesta, reverse("content:interna_calendario"), fetch_redirect_response=False)
                respuesta = self.client.post(
                    reverse("content:editar_pieza", args=[self.en_revision.pk]), {**datos, "estado": "en_revision"}
                )
                self.assertRedirects(respuesta, reverse("content:interna_calendario"), fetch_redirect_response=False)
        self.assertEqual(self.PiezaContenido.all_objects.count(), 2)
        self.en_revision.refresh_from_db()
        self.assertEqual(self.en_revision.version, 1)
        self.assertFalse(self.en_revision.historial_versiones.exists())

    def test_filtro_con_cliente_mal_escrito_no_da_500(self):
        self.client.force_login(self.colab)
        respuesta = self.client.get(reverse("content:interna_calendario"), {"cliente_id": "abc"})
        self.assertEqual(respuesta.status_code, 200)

    # --- Historial: hora local, URL del almacenamiento y sin duplicados ----------------------------

    def test_historial_muestra_la_hora_de_chile(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        self.en_revision.fecha_programada = datetime(2026, 11, 20, 10, 0, tzinfo=ZoneInfo("America/Santiago"))
        self.en_revision.save()
        self.client.force_login(self.aprobador_a)
        datos = self.client.get(reverse("content:obtener_historial_pieza", args=[self.en_revision.pk])).json()
        self.assertEqual(datos["actual"]["fecha_programada"], "20-11-2026 10:00")

    def test_historial_usa_la_url_del_almacenamiento_para_todas_las_versiones(self):
        from unittest import mock

        self.en_revision.archivo = "clientes/1/piezas/foto.jpg"
        self.en_revision.save()
        self.client.force_login(self.colab)
        self.client.post(reverse("content:editar_pieza", args=[self.en_revision.pk]), {**self.datos, "estado": "en_revision"})
        with mock.patch("apps.content.views.default_storage") as almacenamiento:
            almacenamiento.url.side_effect = lambda nombre: f"https://bucket.example/{nombre}?firma=1"
            datos = self.client.get(reverse("content:obtener_historial_pieza", args=[self.en_revision.pk])).json()
        esperado = "https://bucket.example/clientes/1/piezas/foto.jpg?firma=1"
        self.assertEqual(datos["actual"]["archivo"], esperado)
        self.assertEqual(datos["historial"][0]["archivo"], esperado)

    def test_rechazo_y_correccion_no_duplican_versiones(self):
        self.client.force_login(self.aprobador_a)
        self._evaluar(self.en_revision, accion="rechazar", comentario="Cambia la foto")
        self.client.force_login(self.colab)
        self.client.post(reverse("content:editar_pieza", args=[self.en_revision.pk]), {**self.datos, "estado": "en_revision"})
        self.en_revision.refresh_from_db()
        self.assertEqual(list(self.en_revision.historial_versiones.values_list("version", flat=True)), [1])
        # La v2 es nueva: la evaluación del cliente era de la v1.
        self.assertIsNone(self.en_revision.aprobado_por)
        self.client.force_login(self.aprobador_a)
        self._evaluar(self.en_revision)
        datos = self.client.get(reverse("content:obtener_historial_pieza", args=[self.en_revision.pk])).json()
        self.assertEqual([v["version"] for v in datos["historial"]], [1])
        self.assertEqual(datos["historial"][0]["estado_al_guardar"], "Rechazado")
        self.assertEqual(datos["actual"]["estado"], "Aprobado")
        self.assertIsNotNone(datos["actual"]["fecha_aprobacion"])

    # --- Panel interno -----------------------------------------------------------------------------

    def test_filtro_por_estado(self):
        self.client.force_login(self.colab)
        respuesta = self.client.get(reverse("content:interna_calendario"), {"estado": "borrador"})
        self.assertEqual([p.pk for p in respuesta.context["piezas"]], [self.borrador.pk])

    def test_personal_sin_rol_ve_los_mismos_clientes_en_los_que_puede_crear(self):
        personal = get_user_model().objects.create_user("st", "st@x.cl", "x", is_staff=True)
        self.client.force_login(personal)
        respuesta = self.client.get(reverse("content:interna_calendario"))
        self.assertEqual(set(respuesta.context["clientes"]), {self.a, self.b})

    def test_no_se_crean_piezas_en_clientes_inactivos(self):
        self.a.activo = False
        self.a.save()
        self.client.force_login(self.colab)
        respuesta = self.client.post(reverse("content:crear_pieza"), {**self.datos, "estado": "borrador"})
        self.assertEqual(respuesta.status_code, 404)

    def test_observacion_mostrada_es_la_del_cliente(self):
        from apps.content.models import ComentarioPieza

        self.client.force_login(self.aprobador_a)
        self._evaluar(self.en_revision, accion="rechazar", comentario="Cambia la foto")
        ComentarioPieza.objects.create(pieza=self.en_revision, usuario=self.colab, comentario="Lo vemos mañana")
        self.client.force_login(self.colab)
        respuesta = self.client.get(reverse("content:interna_calendario"))
        self.assertEqual(respuesta.context["piezas_rechazadas"][0].observacion_cliente.comentario, "Cambia la foto")

    # --- Correo de pieza en revisión ---------------------------------------------------------------

    def test_correo_en_revision_con_fecha_local_y_solo_a_cuentas_activas(self):
        from django.core import mail

        User = get_user_model()
        User.objects.create_user("pend", "pend@x.cl", None, rol=Rol.CLIENTE_APROBADOR, cliente=self.a)
        User.objects.create_user("baja", "baja@x.cl", "x", rol=Rol.CLIENTE_APROBADOR, cliente=self.a, is_active=False)
        self.client.force_login(self.colab)
        self.client.post(reverse("content:crear_pieza"), {**self.datos, "estado": "en_revision"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["apa@x.cl"])
        self.assertIn("20-11-2026 10:00", mail.outbox[0].body)
