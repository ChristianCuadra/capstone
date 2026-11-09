from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Rol
from apps.ai.models import RegistroIA
from apps.clients.models import Cliente
from apps.metrics.models import Fuente, MetricaDiaria
from apps.notifications.models import Notificacion

from .models import ReporteMensual


class ReportesTests(TestCase):
    """PC-IA-02 (borrador con IA), PC-IA-04 (aprobación humana) y PC-REP-01 (descarga en el portal)."""

    def setUp(self):
        User = get_user_model()
        self.a = Cliente.objects.create(nombre="Alfa", rubro="Gastronomía")
        self.b = Cliente.objects.create(nombre="Beta")
        self.admin = User.objects.create_user("adm", "adm@x.cl", "x", rol=Rol.ADMINISTRADORA, is_staff=True)
        self.colab_a = User.objects.create_user("ca", "ca@x.cl", "x", rol=Rol.COLABORADORA, is_staff=True)
        self.colab_a.clientes_asignados.set([self.a])
        self.lec_a = User.objects.create_user("lea", "lea@x.cl", "x", rol=Rol.CLIENTE_LECTOR, cliente=self.a)
        self.lec_b = User.objects.create_user("leb", "leb@x.cl", "x", rol=Rol.CLIENTE_LECTOR, cliente=self.b)
        MetricaDiaria.all_objects.create(cliente=self.a, fecha=date(2026, 10, 5), fuente=Fuente.INSTAGRAM, alcance=1234, interacciones=99)
        MetricaDiaria.all_objects.create(cliente=self.b, fecha=date(2026, 10, 5), fuente=Fuente.INSTAGRAM, alcance=777777)

    def _generar(self, con_ia="1", usuario=None):
        self.client.force_login(usuario or self.admin)
        return self.client.post(reverse("reports:generar"), {"cliente": self.a.pk, "mes": "2026-10", "con_ia": con_ia})

    @override_settings(AI_API_KEY="clave", AI_MODEL="modelo")
    def test_borrador_con_ia_usa_solo_datos_del_cliente(self):
        with mock.patch("apps.ai.services._llamar_modelo", return_value=("1. Resumen del mes\nBuen mes.", 10, 20, "gemini", "modelo")) as llamada:
            self._generar()
        prompt = llamada.call_args.args[1]
        self.assertIn("1.234", prompt)
        self.assertNotIn("777.777", prompt)
        self.assertNotIn("Beta", prompt)
        reporte = ReporteMensual.all_objects.get()
        self.assertTrue(reporte.generado_con_ia)
        self.assertEqual(reporte.estado, ReporteMensual.Estado.BORRADOR)
        self.assertTrue(RegistroIA.objects.filter(tipo=RegistroIA.Tipo.REPORTE_MENSUAL, cliente=self.a).exists())

    def test_sin_ia_crea_plantilla_editable(self):
        self._generar(con_ia="1")  # sin clave configurada
        reporte = ReporteMensual.all_objects.get()
        self.assertFalse(reporte.generado_con_ia)
        self.assertIn("Alcance", reporte.contenido)

    def test_el_cliente_no_ve_borradores(self):
        self._generar("0")
        reporte = ReporteMensual.all_objects.get()
        self.client.force_login(self.lec_a)
        self.assertEqual(self.client.get(reverse("reports:pdf_portal", args=[reporte.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("content:metricas")), "Descargar PDF")

    def test_editar_y_aprobar_publica_y_avisa(self):
        self._generar("0")
        reporte = ReporteMensual.all_objects.get()
        self.client.post(reverse("reports:editar", args=[reporte.pk]), {"contenido": "Texto revisado por la agencia", "accion": "aprobar"})
        reporte.refresh_from_db()
        self.assertEqual((reporte.estado, reporte.aprobado_por, reporte.contenido), (ReporteMensual.Estado.APROBADO, self.admin, "Texto revisado por la agencia"))
        self.assertTrue(Notificacion.objects.filter(usuario=self.lec_a).exists())
        self.client.force_login(self.lec_a)
        respuesta = self.client.get(reverse("reports:pdf_portal", args=[reporte.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.assertTrue(respuesta.content.startswith(b"%PDF"))

    def test_colaboradora_no_aprueba(self):
        self._generar("0", usuario=self.colab_a)
        reporte = ReporteMensual.all_objects.get()
        self.client.post(reverse("reports:editar", args=[reporte.pk]), {"contenido": "x", "accion": "aprobar"})
        reporte.refresh_from_db()
        self.assertEqual(reporte.estado, ReporteMensual.Estado.BORRADOR)

    def test_aprobado_no_se_edita_ni_regenera(self):
        self._generar("0")
        reporte = ReporteMensual.all_objects.get()
        self.client.post(reverse("reports:editar", args=[reporte.pk]), {"contenido": "Final", "accion": "aprobar"})
        self.client.post(reverse("reports:editar", args=[reporte.pk]), {"contenido": "Cambio", "accion": "guardar"})
        self._generar("0")
        reporte.refresh_from_db()
        self.assertEqual(reporte.contenido, "Final")

    def test_otro_cliente_no_descarga(self):
        self._generar("0")
        reporte = ReporteMensual.all_objects.get()
        self.client.post(reverse("reports:editar", args=[reporte.pk]), {"contenido": "Final", "accion": "aprobar"})
        self.client.force_login(self.lec_b)
        self.assertEqual(self.client.get(reverse("reports:pdf_portal", args=[reporte.pk])).status_code, 404)

    def test_pdf_con_caracteres_especiales(self):
        self._generar("0")
        reporte = ReporteMensual.all_objects.get()
        reporte.contenido = "1. Resumen — “comillas” y emoji 🚀, ñandú"
        reporte.save()
        respuesta = self.client.get(reverse("reports:pdf_panel", args=[reporte.pk]))
        self.assertTrue(respuesta.content.startswith(b"%PDF"))


class PantallasNuevasTests(TestCase):
    """Todas las pantallas nuevas del Sprint 3 y 4 cargan con datos, para cada tipo de usuario."""

    def test_pantallas_cargan(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.catalog.models import Plan, PlanEntregable, TipoEntregable
        from apps.clients.models import KPICliente, MedicionKPI
        from apps.content.models import EstadoPieza, PiezaContenido, Solicitud
        from django.utils import timezone

        User = get_user_model()
        tipo = TipoEntregable.objects.create(nombre="Post T", nombre_plural="posts", slug="post-t", tiene_cuota=True)
        plan = Plan.objects.create(nombre="Plan P", slug="plan-p", precio_mensual=1)
        PlanEntregable.objects.create(plan=plan, tipo_entregable=tipo, cantidad_mensual=3)
        cliente = Cliente.objects.create(nombre="Alfa", plan=plan)
        admin = User.objects.create_user("adm", "adm@x.cl", "x", rol=Rol.ADMINISTRADORA, is_staff=True)
        apr = User.objects.create_user("apa", "apa@x.cl", "x", rol=Rol.CLIENTE_APROBADOR, cliente=cliente)
        hoy = timezone.localdate()
        PiezaContenido.all_objects.create(cliente=cliente, titulo="P1", tipo_entregable=tipo, estado=EstadoPieza.EN_REVISION, texto_generado_ia=True, fecha_programada=timezone.now())
        MetricaDiaria.all_objects.create(cliente=cliente, fecha=hoy, fuente=Fuente.INSTAGRAM, alcance=10, interacciones=2, seguidores=100, gasto=1000, resultados=1)
        kpi = KPICliente.all_objects.create(cliente=cliente, indicador="seguidores", valor_inicial=50, meta=150)
        MedicionKPI.all_objects.create(cliente=cliente, kpi=kpi, fecha=hoy, valor=100)

        self.client.force_login(apr)
        self.client.post(reverse("content:solicitudes"), {"asunto": "Logo", "texto": "Hola", "archivos": [SimpleUploadedFile("a.pdf", b"x")]})
        solicitud = Solicitud.all_objects.get()
        for url in (reverse("content:calendario"), reverse("content:metricas"), reverse("content:solicitudes"),
                    reverse("content:solicitud", args=[solicitud.pk]), reverse("notifications:lista")):
            with self.subTest(url=url, usuario="cliente"):
                self.assertEqual(self.client.get(url).status_code, 200)

        self.client.force_login(admin)
        self.client.post(reverse("reports:generar"), {"cliente": cliente.pk, "mes": hoy.strftime("%Y-%m"), "con_ia": "0"})
        reporte = ReporteMensual.all_objects.get()
        for url in (reverse("content:interna_calendario"), reverse("content:panel_cumplimiento"), reverse("content:panel_solicitudes"),
                    reverse("content:panel_solicitud", args=[solicitud.pk]), reverse("metrics:panel"),
                    reverse("reports:editar", args=[reporte.pk]), reverse("notifications:lista"), reverse("crm:dashboard")):
            with self.subTest(url=url, usuario="admin"):
                respuesta = self.client.get(url)
                self.assertEqual(respuesta.status_code, 200)
        self.assertContains(self.client.get(reverse("content:interna_calendario")), "Generar copy con IA")
        self.assertContains(self.client.get(reverse("metrics:panel")), "KPIs comprometidos")
