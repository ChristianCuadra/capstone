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
