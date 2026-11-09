from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Rol
from apps.clients.models import Cliente

from .models import CorreoSaliente, Notificacion
from .services import MAX_INTENTOS, equipo_del_cliente, notificar, reintentar_pendientes, usuarios_del_cliente


class NotificacionesTests(TestCase):
    """PC-SOL-02: aviso en la plataforma + correo, reintento si falla y destinatarios correctos."""

    def setUp(self):
        User = get_user_model()
        self.a = Cliente.objects.create(nombre="Alfa")
        self.b = Cliente.objects.create(nombre="Beta")
        self.admin = User.objects.create_user("adm", "adm@x.cl", "x", rol=Rol.ADMINISTRADORA, is_staff=True)
        self.colab_a = User.objects.create_user("ca", "ca@x.cl", "x", rol=Rol.COLABORADORA, is_staff=True)
        self.colab_a.clientes_asignados.set([self.a])
        self.colab_b = User.objects.create_user("cb", "cb@x.cl", "x", rol=Rol.COLABORADORA, is_staff=True)
        self.colab_b.clientes_asignados.set([self.b])
        self.apr_a = User.objects.create_user("apa", "apa@x.cl", "x", rol=Rol.CLIENTE_APROBADOR, cliente=self.a)
        self.lec_a = User.objects.create_user("lea", "lea@x.cl", "x", rol=Rol.CLIENTE_LECTOR, cliente=self.a)
        self.apr_b = User.objects.create_user("apb", "apb@x.cl", "x", rol=Rol.CLIENTE_APROBADOR, cliente=self.b)

    def test_crea_aviso_y_correo(self):
        notificar([self.apr_a], "Hola", "mensaje", url="/portal/")
        self.assertEqual(Notificacion.objects.filter(usuario=self.apr_a).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(CorreoSaliente.objects.get().estado, CorreoSaliente.Estado.ENVIADO)

    def test_destinatarios_solo_de_lo_que_les_corresponde(self):
        equipo = set(equipo_del_cliente(self.a))
        self.assertIn(self.admin, equipo)
        self.assertIn(self.colab_a, equipo)
        self.assertNotIn(self.colab_b, equipo)
        self.assertEqual(set(usuarios_del_cliente(self.a)), {self.apr_a, self.lec_a})
        self.assertEqual(set(usuarios_del_cliente(self.a, solo_aprobadores=True)), {self.apr_a})

    def test_si_falla_el_correo_queda_pendiente_y_se_reintenta(self):
        with mock.patch("apps.notifications.services.send_mail", side_effect=OSError("sin servidor")):
            notificar([self.apr_a], "Hola", "mensaje")
        correo = CorreoSaliente.objects.get()
        self.assertEqual(correo.estado, CorreoSaliente.Estado.PENDIENTE)
        self.assertEqual(correo.intentos, 1)
        self.assertIn("sin servidor", correo.ultimo_error)
        # La notificación en la plataforma sí quedó, aunque el correo falló.
        self.assertTrue(Notificacion.objects.filter(usuario=self.apr_a).exists())
        # Antes del plazo no se reintenta; vencido el plazo, sí.
        self.assertEqual(reintentar_pendientes(), (0, 0))
        CorreoSaliente.objects.update(proximo_intento=timezone.now() - timedelta(seconds=1))
        self.assertEqual(reintentar_pendientes(), (1, 1))
        correo.refresh_from_db()
        self.assertEqual(correo.estado, CorreoSaliente.Estado.ENVIADO)
        self.assertEqual(correo.intentos, 2)

    def test_tras_el_maximo_de_intentos_queda_fallido(self):
        with mock.patch("apps.notifications.services.send_mail", side_effect=OSError("caído")):
            notificar([self.apr_a], "Hola")
            for _ in range(MAX_INTENTOS):
                CorreoSaliente.objects.update(proximo_intento=timezone.now() - timedelta(seconds=1))
                reintentar_pendientes()
        correo = CorreoSaliente.objects.get()
        self.assertEqual(correo.estado, CorreoSaliente.Estado.FALLIDO)
        self.assertEqual(correo.intentos, MAX_INTENTOS)

    def test_no_avisa_a_inactivos_ni_duplica(self):
        self.lec_a.is_active = False
        self.lec_a.save()
        self.assertEqual(notificar([self.apr_a, self.apr_a, self.lec_a], "Hola"), 1)

    def test_lista_y_abrir_marca_leida(self):
        notificar([self.apr_a], "Pieza por aprobar", url=reverse("content:aprobacion"))
        aviso = Notificacion.objects.get()
        self.client.force_login(self.apr_a)
        respuesta = self.client.get(reverse("notifications:lista"))
        self.assertContains(respuesta, "Pieza por aprobar")
        self.assertEqual(respuesta.context["notificaciones_sin_leer"], 1)
        self.assertRedirects(self.client.get(reverse("notifications:abrir", args=[aviso.pk])), reverse("content:aprobacion"), fetch_redirect_response=False)
        aviso.refresh_from_db()
        self.assertTrue(aviso.leida)

    def test_no_se_puede_abrir_aviso_ajeno(self):
        notificar([self.apr_b], "De Beta")
        self.client.force_login(self.apr_a)
        aviso = Notificacion.objects.get()
        self.assertEqual(self.client.get(reverse("notifications:abrir", args=[aviso.pk])).status_code, 404)

    def test_equipo_ve_notificaciones_en_el_panel(self):
        notificar([self.colab_a], "Nueva solicitud")
        self.client.force_login(self.colab_a)
        respuesta = self.client.get(reverse("notifications:lista"))
        self.assertContains(respuesta, "Nueva solicitud")
        self.assertTemplateUsed(respuesta, "crm/base_panel.html")

    def test_comando_reintentar(self):
        from io import StringIO

        from django.core.management import call_command

        salida = StringIO()
        call_command("reintentar_correos", stdout=salida)
        self.assertIn("Correos revisados: 0", salida.getvalue())


class ListaNotificacionesTests(TestCase):
    """Al abrir o marcar leída, el aviso sale de la lista; las leídas quedan en su pestaña."""

    def setUp(self):
        self.u = get_user_model().objects.create_user("apa", "apa@x.cl", "x", rol=Rol.CLIENTE_APROBADOR)
        self.otro = get_user_model().objects.create_user("otro", "otro@x.cl", "x", rol=Rol.CLIENTE_APROBADOR)
        self.a1 = Notificacion.objects.create(usuario=self.u, titulo="Aviso uno")
        self.a2 = Notificacion.objects.create(usuario=self.u, titulo="Aviso dos")
        self.client.force_login(self.u)

    def test_abrir_lo_saca_de_sin_leer_y_queda_en_leidas(self):
        self.client.get(reverse("notifications:abrir", args=[self.a1.pk]))
        sin_leer = self.client.get(reverse("notifications:lista"))
        self.assertNotContains(sin_leer, "Aviso uno")
        self.assertContains(sin_leer, "Aviso dos")
        self.assertContains(self.client.get(reverse("notifications:lista"), {"ver": "leidas"}), "Aviso uno")

    def test_marcar_una_sin_abrirla(self):
        self.client.post(reverse("notifications:marcar_leida", args=[self.a2.pk]))
        self.a2.refresh_from_db()
        self.assertTrue(self.a2.leida)

    def test_marcar_todas_deja_la_lista_vacia(self):
        self.client.post(reverse("notifications:marcar_todas"))
        self.assertContains(self.client.get(reverse("notifications:lista")), "Estás al día")

    def test_no_marca_avisos_ajenos(self):
        ajeno = Notificacion.objects.create(usuario=self.otro, titulo="Ajeno")
        self.client.post(reverse("notifications:marcar_leida", args=[ajeno.pk]))
        ajeno.refresh_from_db()
        self.assertFalse(ajeno.leida)
