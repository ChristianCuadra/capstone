from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import Rol
from apps.catalog.models import Plan, PlanEntregable, TipoEntregable
from apps.clients.models import Cliente
from apps.content.cumplimiento import cumplimiento_cliente
from apps.content.models import PiezaContenido, Solicitud
from apps.metrics.models import MetricaDiaria
from apps.reports.models import ReporteMensual


class CargarDemoTests(TestCase):
    def setUp(self):
        User = get_user_model()
        tipo = TipoEntregable.objects.create(nombre="Post demo", nombre_plural="posts", slug="post-demo-t", tiene_cuota=True)
        self.plan = Plan.objects.create(nombre="Plan demo T", slug="plan-demo-t", precio_mensual=1000, orden=0)
        PlanEntregable.objects.create(plan=self.plan, tipo_entregable=tipo, cantidad_mensual=6)
        self.a = Cliente.objects.create(nombre="Alfa", plan=self.plan)
        self.b = Cliente.objects.create(nombre="Beta", plan=self.plan)
        User.objects.create_user("adm", "adm@x.cl", "x", rol=Rol.ADMINISTRADORA, is_staff=True)
        User.objects.create_user("cliente.prueba", "c@x.cl", "x", rol=Rol.CLIENTE_APROBADOR, cliente=self.a)

    def test_carga_solo_en_el_cliente_y_se_puede_borrar(self):
        call_command("cargar_demo", stdout=StringIO())
        self.assertGreater(PiezaContenido.all_objects.filter(cliente=self.a).count(), 6)
        self.assertEqual(PiezaContenido.all_objects.filter(cliente=self.b).count(), 0)
        self.assertEqual(Solicitud.all_objects.filter(cliente=self.a).count(), 2)
        self.assertTrue(MetricaDiaria.all_objects.filter(cliente=self.a).exists())
        self.assertEqual(ReporteMensual.all_objects.filter(cliente=self.a, estado="aprobado").count(), 1)
        from django.utils import timezone
        filas = cumplimiento_cliente(self.a, timezone.localdate().replace(day=1))
        self.assertTrue(filas)
        # una segunda carga no duplica
        call_command("cargar_demo", stdout=StringIO())
        self.assertEqual(Solicitud.all_objects.filter(cliente=self.a).count(), 2)
        call_command("cargar_demo", "--borrar", stdout=StringIO())
        self.assertEqual(PiezaContenido.all_objects.filter(cliente=self.a).count(), 0)
        self.assertEqual(Solicitud.all_objects.filter(cliente=self.a).count(), 0)
        self.assertFalse(MetricaDiaria.all_objects.filter(cliente=self.a).exists())
        self.assertEqual(ReporteMensual.all_objects.filter(cliente=self.a).count(), 0)
