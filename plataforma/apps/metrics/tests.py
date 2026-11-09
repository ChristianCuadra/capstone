from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Rol
from apps.clients.models import Cliente

from .importador import ErrorArchivo, _numero, leer_archivo
from .models import Fuente, ImportacionMetricas, MetricaDiaria
from .resumen import resumen_metricas

CSV_OK = (
    "Fecha;Alcance;Impresiones;Interacciones;Seguidores;Clics;Importe gastado (CLP);Resultados\n"
    "01-11-2026;1.200;2.500;180;3.450;40;15.000;3\n"
    "02-11-2026;800;1.600;120;3.470;25;10.000,50;2\n"
)


def _csv(texto, nombre="metricas.csv"):
    return SimpleUploadedFile(nombre, texto.encode("utf-8"), content_type="text/csv")


class ImportadorTests(TestCase):
    """PC-MET-01 · Lectura y validación del archivo."""

    def test_lee_plantilla_con_formato_chileno(self):
        filas = leer_archivo(_csv(CSV_OK))
        self.assertEqual(filas[0]["fecha"], date(2026, 11, 1))
        self.assertEqual(filas[0]["alcance"], 1200)
        self.assertEqual(filas[1]["gasto"], Decimal("10000.50"))

    def test_acepta_encabezados_de_meta_en_ingles_y_coma(self):
        filas = leer_archivo(_csv("Reporting starts,Reach,Impressions,Link clicks,Amount spent (CLP),Results\n2026-11-03,1500,3000,60,\"12,000\",4\n"))
        self.assertEqual((filas[0]["fecha"], filas[0]["alcance"], filas[0]["gasto"]), (date(2026, 11, 3), 1500, Decimal("12000.00")))

    def test_lee_excel(self):
        import io

        from openpyxl import Workbook

        libro = Workbook()
        hoja = libro.active
        hoja.append(["Fecha", "Alcance", "Seguidores"])
        hoja.append([date(2026, 11, 5), 900, 3500])
        buffer = io.BytesIO()
        libro.save(buffer)
        archivo = SimpleUploadedFile("m.xlsx", buffer.getvalue())
        self.assertEqual(leer_archivo(archivo)[0]["seguidores"], 3500)

    def test_errores_con_fila_y_columna(self):
        with self.assertRaises(ErrorArchivo) as ctx:
            leer_archivo(_csv("Fecha;Alcance\n01-11-2026;abc\n32-11-2026;10\n01-11-2026;-5\n"))
        texto = " ".join(ctx.exception.errores)
        self.assertIn("Fila 2, alcance", texto)
        self.assertIn("Fila 3, fecha", texto)
        self.assertIn("negativo", texto)
        self.assertIn("ya aparece en la fila 2", texto)

    def test_sin_columnas_reconocibles(self):
        with self.assertRaises(ErrorArchivo):
            leer_archivo(_csv("Nombre;Valor\nx;1\n"))

    def test_formato_no_permitido(self):
        with self.assertRaises(ErrorArchivo):
            leer_archivo(SimpleUploadedFile("m.pdf", b"%PDF"))

    def test_numeros(self):
        self.assertEqual(_numero("1.234"), 1234)
        self.assertEqual(_numero("1,234"), 1234)
        self.assertEqual(_numero("1.234,56", decimal=True), Decimal("1234.56"))
        self.assertEqual(_numero("1234.56", decimal=True), Decimal("1234.56"))
        self.assertIsNone(_numero(""))


class MetricasVistasTests(TestCase):
    """PC-MET-01 (carga), PC-DSH-01 (dashboard agencia) y PC-DSH-02 (portal)."""

    def setUp(self):
        User = get_user_model()
        self.a = Cliente.objects.create(nombre="Alfa")
        self.b = Cliente.objects.create(nombre="Beta")
        self.admin = User.objects.create_user("adm", "adm@x.cl", "x", rol=Rol.ADMINISTRADORA, is_staff=True)
        self.colab_b = User.objects.create_user("cb", "cb@x.cl", "x", rol=Rol.COLABORADORA, is_staff=True)
        self.colab_b.clientes_asignados.set([self.b])
        self.lec_a = User.objects.create_user("lea", "lea@x.cl", "x", rol=Rol.CLIENTE_LECTOR, cliente=self.a)
        self.lec_b = User.objects.create_user("leb", "leb@x.cl", "x", rol=Rol.CLIENTE_LECTOR, cliente=self.b)

    def _cargar(self, texto=CSV_OK, cliente=None, usuario=None):
        self.client.force_login(usuario or self.admin)
        return self.client.post(reverse("metrics:importar"), {
            "cliente": (cliente or self.a).pk, "fuente": Fuente.INSTAGRAM, "archivo": _csv(texto),
        })

    def test_administradora_carga_y_aparece_en_el_dashboard(self):
        self._cargar()
        self.assertEqual(MetricaDiaria.all_objects.filter(cliente=self.a).count(), 2)
        respuesta = self.client.get(reverse("metrics:panel"), {"cliente": self.a.pk, "desde": "2026-11-01", "hasta": "2026-11-30"})
        resumen = respuesta.context["resumen"]
        self.assertTrue(resumen["hay_datos"])
        self.assertEqual(resumen["totales"]["alcance"], 2000)
        self.assertEqual(resumen["seguidores"], 3470)
        self.assertEqual(resumen["nuevos_seguidores"], 20)

    def test_archivo_con_errores_no_carga_nada(self):
        self._cargar("Fecha;Alcance\n01-11-2026;100\n02-11-2026;xx\n")
        self.assertFalse(MetricaDiaria.all_objects.exists())
        self.assertFalse(ImportacionMetricas.all_objects.exists())

    def test_cargar_de_nuevo_reemplaza_sin_duplicar(self):
        self._cargar()
        self._cargar("Fecha;Alcance\n01-11-2026;5000\n")
        self.assertEqual(MetricaDiaria.all_objects.filter(cliente=self.a).count(), 2)
        self.assertEqual(MetricaDiaria.all_objects.get(cliente=self.a, fecha=date(2026, 11, 1)).alcance, 5000)

    def test_colaboradora_no_carga_ni_ve_otros_clientes(self):
        self._cargar(cliente=self.b, usuario=self.colab_b)
        self.assertFalse(MetricaDiaria.all_objects.exists())
        self.client.force_login(self.colab_b)
        self.assertEqual(self.client.get(reverse("metrics:panel"), {"cliente": self.a.pk}).status_code, 404)

    def test_filtro_por_rango_de_fechas(self):
        self._cargar()
        r = resumen_metricas(self.a, date(2026, 11, 2), date(2026, 11, 2))
        self.assertEqual(r["totales"]["alcance"], 800)
        self.assertFalse(resumen_metricas(self.a, date(2026, 10, 1), date(2026, 10, 31))["hay_datos"])

    def test_estado_vacio_claro(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("metrics:panel"), {"cliente": self.a.pk})
        self.assertContains(respuesta, "Sin métricas en este período")

    def test_portal_muestra_solo_su_empresa_y_coincide_con_la_agencia(self):
        self._cargar()
        self._cargar("Fecha;Alcance\n01-11-2026;99999\n", cliente=self.b)
        params = {"desde": "2026-11-01", "hasta": "2026-11-30"}
        self.client.force_login(self.lec_a)
        portal = self.client.get(reverse("content:metricas"), params).context["resumen"]
        self.client.force_login(self.admin)
        panel = self.client.get(reverse("metrics:panel"), {**params, "cliente": self.a.pk}).context["resumen"]
        self.assertEqual(portal["indicadores"], panel["indicadores"])
        self.assertEqual(portal["totales"]["alcance"], 2000)

    def test_plantilla_descargable(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("metrics:plantilla"))
        self.assertIn("Fecha;Alcance", respuesta.content.decode("utf-8-sig"))
        filas = leer_archivo(SimpleUploadedFile("p.csv", respuesta.content))
        self.assertEqual(len(filas), 1)

    def test_cliente_no_entra_al_panel_de_metricas(self):
        self.client.force_login(self.lec_a)
        self.assertEqual(self.client.get(reverse("metrics:panel")).status_code, 302)
