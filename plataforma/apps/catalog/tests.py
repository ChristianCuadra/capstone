from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Plan, PlanEntregable, TipoEntregable
from .services import comparativa_de_planes, planes_del_sitio


class CatalogoInicialTests(TestCase):
    """La migración 0002 carga el catálogo vigente de la agencia."""

    def test_planes_y_precios(self):
        precios = dict(Plan.objects.values_list("slug", "precio_mensual"))
        self.assertEqual(precios, {"presencia": 150000, "posicionamiento": 200000, "crecimiento": 300000, "expansion": 350000})
        self.assertEqual(Plan.objects.get(slug="expansion").precio_primer_mes, 400000)

    def test_presencia_suma_20_piezas(self):
        cuotas = PlanEntregable.objects.filter(plan__slug="presencia", tipo_entregable__tiene_cuota=True)
        self.assertEqual(sum(c.cantidad_mensual for c in cuotas), 20)

    def test_cada_plan_incluye_todo_el_anterior(self):
        planes = list(Plan.objects.order_by("precio_mensual"))
        for menor, mayor in zip(planes, planes[1:]):
            with self.subTest(menor=menor.slug, mayor=mayor.slug):
                self.assertLess(set(menor.tipos_entregable.all()), set(mayor.tipos_entregable.all()))


class PlanEntregableTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(nombre="Pyme", slug="pyme", precio_mensual=90000)
        self.historia = TipoEntregable.objects.get(slug="historia")
        self.branding = TipoEntregable.objects.get(slug="branding")

    def test_texto(self):
        self.assertEqual(PlanEntregable(plan=self.plan, tipo_entregable=self.historia, cantidad_mensual=8).texto, "8 historias")
        self.assertEqual(PlanEntregable(plan=self.plan, tipo_entregable=self.branding).texto, "Branding")

    def test_entregable_con_cuota_exige_cantidad(self):
        with self.assertRaises(ValidationError):
            PlanEntregable(plan=self.plan, tipo_entregable=self.historia).full_clean()

    def test_entregable_sin_cuota_no_acepta_cantidad(self):
        with self.assertRaises(ValidationError):
            PlanEntregable(plan=self.plan, tipo_entregable=self.branding, cantidad_mensual=2).full_clean()

    def test_plan_nuevo_aparece_en_comparativa(self):
        PlanEntregable.objects.create(plan=self.plan, tipo_entregable=self.historia, cantidad_mensual=8)
        planes = planes_del_sitio()
        self.assertEqual(planes[0]["nombre"], "Pyme")  # el más barato va primero
        fila = next(f for f in comparativa_de_planes(planes) if f["caracteristica"] == "Historias al mes")
        self.assertEqual([c["valor"] for c in fila["celdas"]], [8, 16, 16, 16, 16])
