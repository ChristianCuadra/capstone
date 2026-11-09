from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Rol
from apps.clients.models import Cliente
from apps.notifications.models import Notificacion

from .models import ArchivoSolicitud, Solicitud


def _archivo(nombre="brief.pdf", contenido=b"%PDF-1.4 prueba", tipo="application/pdf"):
    return SimpleUploadedFile(nombre, contenido, content_type=tipo)


class SolicitudesTests(TestCase):
    """PC-SOL-01 · Solicitudes y archivos, con sus avisos (PC-SOL-02)."""

    def setUp(self):
        User = get_user_model()
        self.a = Cliente.objects.create(nombre="Alfa")
        self.b = Cliente.objects.create(nombre="Beta")
        self.admin = User.objects.create_user("adm", "adm@x.cl", "x", rol=Rol.ADMINISTRADORA, is_staff=True)
        self.colab_b = User.objects.create_user("cb", "cb@x.cl", "x", rol=Rol.COLABORADORA, is_staff=True)
        self.colab_b.clientes_asignados.set([self.b])
        self.lec_a = User.objects.create_user("lea", "lea@x.cl", "x", rol=Rol.CLIENTE_LECTOR, cliente=self.a)
        self.apr_a = User.objects.create_user("apa", "apa@x.cl", "x", rol=Rol.CLIENTE_APROBADOR, cliente=self.a)
        self.apr_b = User.objects.create_user("apb", "apb@x.cl", "x", rol=Rol.CLIENTE_APROBADOR, cliente=self.b)

    def _crear(self, usuario=None, **extra):
        self.client.force_login(usuario or self.lec_a)
        datos = {"asunto": "Cambiar logo", "texto": "Adjunto el logo nuevo", "archivos": [_archivo()], **extra}
        return self.client.post(reverse("content:solicitudes"), datos)

    def test_cliente_lector_envia_solicitud_con_archivo_y_avisa_al_equipo(self):
        respuesta = self._crear()
        solicitud = Solicitud.all_objects.get()
        self.assertRedirects(respuesta, reverse("content:solicitud", args=[solicitud.pk]))
        self.assertEqual(solicitud.cliente, self.a)
        self.assertEqual(ArchivoSolicitud.objects.count(), 1)
        # Aviso a la administradora; la colaboradora de otro cliente no recibe nada.
        self.assertTrue(Notificacion.objects.filter(usuario=self.admin).exists())
        self.assertFalse(Notificacion.objects.filter(usuario=self.colab_b).exists())
        self.assertIn("adm@x.cl", [m.to[0] for m in mail.outbox])

    def test_formato_no_permitido_no_guarda_nada(self):
        self._crear(archivos=[_archivo("virus.exe", b"MZ", "application/octet-stream")])
        self.assertFalse(Solicitud.all_objects.exists())
        self.assertFalse(ArchivoSolicitud.objects.exists())

    def test_archivo_demasiado_grande_no_guarda_nada(self):
        from apps.content import views_solicitudes

        with self.settings():
            original = views_solicitudes.TAMANO_MAX_SOLICITUD_MB
            views_solicitudes.TAMANO_MAX_SOLICITUD_MB = 0
            try:
                self._crear()
            finally:
                views_solicitudes.TAMANO_MAX_SOLICITUD_MB = original
        self.assertFalse(Solicitud.all_objects.exists())

    def test_limite_de_archivos(self):
        self._crear(archivos=[_archivo(f"a{i}.pdf") for i in range(6)])
        self.assertFalse(Solicitud.all_objects.exists())

    def test_agencia_responde_y_avisa_al_cliente(self):
        self._crear()
        solicitud = Solicitud.all_objects.get()
        Notificacion.objects.all().delete()
        self.client.force_login(self.admin)
        self.client.post(reverse("content:panel_solicitud", args=[solicitud.pk]), {"texto": "Listo, lo cambiamos", "archivos": [_archivo("logo.png", b"png", "image/png")]})
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, Solicitud.Estado.RESPONDIDA)
        self.assertEqual(set(Notificacion.objects.values_list("usuario__username", flat=True)), {"lea", "apa"})
        self.client.force_login(self.lec_a)
        respuesta = self.client.get(reverse("content:solicitud", args=[solicitud.pk]))
        self.assertContains(respuesta, "Listo, lo cambiamos")
        self.assertContains(respuesta, "logo.png")

    def test_cliente_no_ve_solicitudes_ni_archivos_de_otra_empresa(self):
        self._crear()
        solicitud = Solicitud.all_objects.get()
        archivo = ArchivoSolicitud.objects.get()
        self.client.force_login(self.apr_b)
        self.assertEqual(self.client.get(reverse("content:solicitud", args=[solicitud.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("content:solicitud_archivo", args=[archivo.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("content:solicitudes")), "Cambiar logo")

    def test_colaboradora_solo_ve_solicitudes_de_sus_clientes(self):
        self._crear()
        solicitud = Solicitud.all_objects.get()
        self.client.force_login(self.colab_b)
        self.assertNotContains(self.client.get(reverse("content:panel_solicitudes")), "Cambiar logo")
        self.assertEqual(self.client.get(reverse("content:panel_solicitud", args=[solicitud.pk])).status_code, 404)

    def test_cliente_no_entra_al_panel_de_solicitudes(self):
        self.client.force_login(self.apr_a)
        respuesta = self.client.get(reverse("content:panel_solicitudes"))
        self.assertEqual(respuesta.status_code, 302)

    def test_descarga_de_archivo(self):
        self._crear()
        archivo = ArchivoSolicitud.objects.get()
        respuesta = self.client.get(reverse("content:solicitud_archivo", args=[archivo.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("brief.pdf", respuesta["Content-Disposition"])
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("content:panel_solicitud_archivo", args=[archivo.pk])).status_code, 200)

    def test_cerrar_impide_responder_al_cliente(self):
        self._crear()
        solicitud = Solicitud.all_objects.get()
        self.client.force_login(self.admin)
        self.client.post(reverse("content:panel_solicitud", args=[solicitud.pk]), {"accion": "cerrar"})
        self.client.force_login(self.lec_a)
        self.client.post(reverse("content:solicitud", args=[solicitud.pk]), {"texto": "otra cosa"})
        self.assertEqual(solicitud.mensajes.count(), 1)

    def test_badge_de_solicitudes_abiertas_en_el_panel(self):
        self._crear()
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("content:panel_solicitudes"))
        self.assertEqual(respuesta.context["panel_badges"]["solicitudes"], 1)
