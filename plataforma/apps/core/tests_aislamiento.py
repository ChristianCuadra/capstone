"""PC-TEC-04 · Suite de pruebas de aislamiento entre clientes y de permisos por rol.

Cubre CP-020 (acceso por URL a un recurso de otro cliente) y CP-021 (manipulación del identificador
de cliente). Criterio de la suite: todo intento de leer datos de otro cliente o de ejecutar una acción
fuera del rol debe quedar denegado, sin revelar la existencia del recurso.

Se ejecuta con el resto de los tests en la integración continua (`python manage.py test apps`).
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.test import TestCase
from django.urls import reverse

from apps.clients.models import Cliente, DocumentoCliente
from apps.core.context import get_allowed_client_ids, reset_allowed_client_ids, set_allowed_client_ids
from apps.core.middleware import SESSION_CLIENT_KEY

User = get_user_model()

# Vistas del panel que cualquier usuario del equipo puede abrir, y las exclusivas de la administradora.
PANEL_EQUIPO = [
    ("crm:dashboard", []), ("crm:prospectos", []), ("crm:prospectos_exportar", []), ("crm:prospecto_nuevo", []),
    ("crm:cotizaciones", []), ("crm:clientes", []), ("crm:planes_servicios", []), ("crm:contenidos", []),
    ("crm:prospecto_detalle", [1]), ("crm:cotizacion_editar", [1]), ("crm:cliente_ficha", [1]),
    ("crm:cliente_documento_descargar", [1, 1]),
]
PANEL_SOLO_ADMIN = [
    ("crm:usuarios", []), ("crm:usuario_nuevo", []), ("crm:usuario_editar", [1]), ("crm:auditoria", []),
    ("crm:usuario_alternar_activo", [1]), ("crm:usuario_restablecer_2fa", [1]), ("crm:usuario_eliminar", [1]),
]
ACCIONES_POST = [
    ("crm:cliente_activo", []), ("crm:cliente_documento_subir", [1]), ("crm:cliente_documento_eliminar", [1, 1]),
    ("crm:prospecto_mover", [1]), ("crm:tarea_crear", []),
]


def _destino(respuesta):
    """Ruta a la que redirige una respuesta, sin el parámetro ?next=."""
    return respuesta["Location"].split("?")[0]


PORTAL = ["content:calendario", "content:aprobacion", "content:metricas"]


class BaseAislamiento(TestCase):
    def setUp(self):
        self._tokens = []
        self.addCleanup(self._restaurar_contexto)
        self.a = Cliente.objects.create(nombre="Panadería Alfa")
        self.b = Cliente.objects.create(nombre="Clínica Beta Secreta")
        self.admin = User.objects.create_user("adm", "adm@x.cl", "x", rol="administradora", is_staff=True)
        self.colab = User.objects.create_user("col", "col@x.cl", "x", rol="colaboradora", is_staff=True)
        self.colab.clientes_asignados.set([self.a])
        self.aprobador_a = User.objects.create_user("apa", "apa@x.cl", "x", rol="cliente_aprobador", cliente=self.a)
        self.lector_a = User.objects.create_user("lea", "lea@x.cl", "x", rol="cliente_lector", cliente=self.a)
        self.doc_b = DocumentoCliente.all_objects.create(
            cliente=self.b, nombre="Contrato Beta", archivo=ContentFile(b"confidencial-b", name="beta.pdf")
        )
        self.doc_a = DocumentoCliente.all_objects.create(
            cliente=self.a, nombre="Contrato Alfa", archivo=ContentFile(b"datos-a", name="alfa.pdf")
        )

    def _restringir(self, ids):
        self._tokens.append(set_allowed_client_ids(ids))

    def _restaurar_contexto(self):
        while self._tokens:
            reset_allowed_client_ids(self._tokens.pop())


class PermisosPorRolTests(BaseAislamiento):
    """Acciones fuera de rol: todas denegadas y sin efectos."""

    def test_anonimo_no_entra_al_panel_ni_al_portal(self):
        for nombre, args in PANEL_EQUIPO + PANEL_SOLO_ADMIN:
            with self.subTest(vista=nombre):
                r = self.client.get(reverse(nombre, args=args))
                self.assertEqual(r.status_code, 302)
                self.assertIn("login", r["Location"])
        for nombre in PORTAL:
            with self.subTest(vista=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 302)

    def test_usuarios_cliente_no_entran_a_ninguna_vista_del_panel(self):
        for usuario in (self.aprobador_a, self.lector_a):
            self.client.force_login(usuario)
            for nombre, args in PANEL_EQUIPO + PANEL_SOLO_ADMIN:
                with self.subTest(usuario=usuario.username, vista=nombre):
                    r = self.client.get(reverse(nombre, args=args))
                    self.assertEqual(r.status_code, 302)
                    self.assertFalse(_destino(r).startswith("/panel/"))

    def test_usuarios_cliente_no_ejecutan_acciones_del_panel(self):
        usuarios_antes = User.objects.count()
        docs_antes = DocumentoCliente.all_objects.count()
        for usuario in (self.aprobador_a, self.lector_a):
            self.client.force_login(usuario)
            for nombre, args in ACCIONES_POST + [("crm:usuario_eliminar", [self.admin.pk]), ("crm:usuario_alternar_activo", [self.admin.pk])]:
                with self.subTest(usuario=usuario.username, accion=nombre):
                    r = self.client.post(reverse(nombre, args=args), {"cliente": self.b.pk})
                    self.assertIn(r.status_code, (302, 403, 404, 405))
                    if r.status_code == 302:
                        self.assertFalse(_destino(r).startswith("/panel/"))
        self.assertEqual(User.objects.count(), usuarios_antes)
        self.assertEqual(DocumentoCliente.all_objects.count(), docs_antes)
        self.assertTrue(User.objects.get(pk=self.admin.pk).is_active)

    def test_colaboradora_no_entra_a_vistas_de_administradora(self):
        self.client.force_login(self.colab)
        for nombre, args in PANEL_SOLO_ADMIN:
            with self.subTest(vista=nombre):
                r = self.client.get(reverse(nombre, args=args))
                self.assertEqual(r.status_code, 302)

    def test_colaboradora_no_gestiona_usuarios_por_post(self):
        self.client.force_login(self.colab)
        antes = User.objects.count()
        self.client.post(reverse("crm:usuario_eliminar", args=[self.lector_a.pk]))
        self.client.post(reverse("crm:usuario_alternar_activo", args=[self.lector_a.pk]))
        self.assertEqual(User.objects.count(), antes)
        self.assertTrue(User.objects.get(pk=self.lector_a.pk).is_active)

    def test_usuario_equipo_no_entra_al_portal_del_cliente(self):
        for usuario in (self.colab, self.admin):
            self.client.force_login(usuario)
            for nombre in PORTAL:
                with self.subTest(usuario=usuario.username, vista=nombre):
                    r = self.client.get(reverse(nombre))
                    self.assertEqual(r.status_code, 302)
                    self.assertFalse(_destino(r).startswith("/portal/"))


class AccesoPorUrlEntreClientesTests(BaseAislamiento):
    """CP-020: pedir por URL un recurso de otro cliente se deniega sin revelar que existe."""

    def _sin_fuga(self, respuesta):
        self.assertNotEqual(respuesta.status_code, 200)
        contenido = getattr(respuesta, "content", b"").decode("utf-8", "ignore")
        for secreto in ("Clínica Beta Secreta", "Contrato Beta", "confidencial-b"):
            self.assertNotIn(secreto, contenido)

    def test_ficha_de_cliente_ajeno_da_404(self):
        self.client.force_login(self.colab)
        r = self.client.get(reverse("crm:cliente_ficha", args=[self.b.pk]))
        self.assertEqual(r.status_code, 404)
        self._sin_fuga(r)

    def test_cliente_inexistente_y_cliente_ajeno_responden_igual(self):
        """No se revela la existencia: 'no existe' y 'no es tuyo' son indistinguibles."""
        self.client.force_login(self.colab)
        ajeno = self.client.get(reverse("crm:cliente_ficha", args=[self.b.pk]))
        inexistente = self.client.get(reverse("crm:cliente_ficha", args=[999999]))
        self.assertEqual(ajeno.status_code, inexistente.status_code)

    def test_documento_ajeno_no_se_descarga_con_ningun_cliente_en_la_url(self):
        self.client.force_login(self.colab)
        for cliente_en_url in (self.a.pk, self.b.pk):
            with self.subTest(cliente_en_url=cliente_en_url):
                r = self.client.get(reverse("crm:cliente_documento_descargar", args=[cliente_en_url, self.doc_b.pk]))
                self._sin_fuga(r)

    def test_documento_ajeno_no_se_elimina(self):
        self.client.force_login(self.colab)
        self.client.post(reverse("crm:cliente_documento_eliminar", args=[self.b.pk, self.doc_b.pk]))
        self.client.post(reverse("crm:cliente_documento_eliminar", args=[self.a.pk, self.doc_b.pk]))
        self.assertTrue(DocumentoCliente.all_objects.filter(pk=self.doc_b.pk).exists())

    def test_no_se_sube_documento_a_cliente_ajeno(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.colab)
        r = self.client.post(
            reverse("crm:cliente_documento_subir", args=[self.b.pk]),
            {"nombre": "Intruso", "tipo": "otro", "archivo": SimpleUploadedFile("x.pdf", b"x")},
        )
        self.assertEqual(r.status_code, 404)
        self.assertFalse(DocumentoCliente.all_objects.filter(nombre="Intruso").exists())

    def test_no_se_edita_ficha_de_cliente_ajeno(self):
        self.client.force_login(self.colab)
        self.client.post(reverse("crm:cliente_ficha", args=[self.b.pk]), {"nombre": "Hackeada", "objetivos": "x"})
        self.b.refresh_from_db()
        self.assertEqual(self.b.nombre, "Clínica Beta Secreta")

    def test_ficha_propia_no_contiene_datos_del_otro_cliente(self):
        self.client.force_login(self.colab)
        r = self.client.get(reverse("crm:cliente_ficha", args=[self.a.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Contrato Alfa")
        self.assertNotContains(r, "Clínica Beta Secreta")
        self.assertNotContains(r, "Contrato Beta")

    def test_listado_y_selector_de_la_colaboradora_no_nombran_al_otro_cliente(self):
        self.client.force_login(self.colab)
        for nombre in ("crm:clientes", "crm:dashboard"):
            with self.subTest(vista=nombre):
                self.assertNotContains(self.client.get(reverse(nombre)), "Clínica Beta Secreta")

    def test_admin_de_django_no_muestra_ni_abre_clientes_ajenos(self):
        self.client.force_login(self.colab)
        lista = self.client.get(reverse("admin:clients_cliente_changelist"))
        self.assertNotContains(lista, "Clínica Beta Secreta", status_code=lista.status_code)
        detalle = self.client.get(reverse("admin:clients_cliente_change", args=[self.b.pk]))
        self.assertNotEqual(detalle.status_code, 200)
        self.assertNotContains(detalle, "Clínica Beta Secreta", status_code=detalle.status_code)

    def test_portal_del_cliente_no_nombra_a_otras_empresas(self):
        self.client.force_login(self.aprobador_a)
        for nombre in PORTAL:
            with self.subTest(vista=nombre):
                r = self.client.get(reverse(nombre))
                self.assertEqual(r.status_code, 200)
                self.assertNotContains(r, "Clínica Beta Secreta")
                self.assertNotContains(r, "Contrato Beta")


class ManipulacionDelIdentificadorDeClienteTests(BaseAislamiento):
    """CP-021: el identificador de cliente enviado por el usuario se ignora o se rechaza."""

    def test_cliente_no_cambia_de_empresa_con_la_sesion(self):
        self.client.force_login(self.aprobador_a)
        sesion = self.client.session
        sesion[SESSION_CLIENT_KEY] = self.b.pk
        sesion.save()
        r = self.client.get(reverse("content:calendario"))
        self.assertEqual(r.wsgi_request.client_id, self.a.pk)

    def test_cliente_no_cambia_de_empresa_con_parametros_de_la_peticion(self):
        self.client.force_login(self.aprobador_a)
        for parametros in ({"cliente": self.b.pk}, {"client_id": self.b.pk}, {"cliente_id": self.b.pk}):
            with self.subTest(parametros=parametros):
                r = self.client.get(reverse("content:metricas"), parametros)
                self.assertEqual(r.wsgi_request.client_id, self.a.pk)
                self.assertNotContains(r, "Clínica Beta Secreta")
                r = self.client.post(reverse("content:aprobacion"), parametros)
                self.assertNotEqual(getattr(r.wsgi_request, "client_id", None), self.b.pk)

    def test_cliente_activo_de_cliente_no_asignado_se_rechaza_y_no_cambia_la_sesion(self):
        self.client.force_login(self.colab)
        self.client.post(reverse("crm:cliente_activo"), {"cliente": self.a.pk})
        r = self.client.post(reverse("crm:cliente_activo"), {"cliente": self.b.pk})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.client.session[SESSION_CLIENT_KEY], self.a.pk)

    def test_valores_basura_como_cliente_activo_no_rompen_ni_filtran(self):
        self.client.force_login(self.colab)
        for valor in ("abc", "-1", "0", "9999999999999999999", "1 OR 1=1", "' OR '1'='1"):
            with self.subTest(valor=valor):
                r = self.client.post(reverse("crm:cliente_activo"), {"cliente": valor})
                self.assertIn(r.status_code, (302, 404))
                self.assertNotEqual(self.client.session.get(SESSION_CLIENT_KEY), self.b.pk)

    def test_id_de_cliente_en_sesion_no_asignado_se_descarta(self):
        self.client.force_login(self.colab)
        sesion = self.client.session
        sesion[SESSION_CLIENT_KEY] = self.b.pk
        sesion.save()
        r = self.client.get(reverse("crm:clientes"))
        self.assertNotContains(r, "Clínica Beta Secreta")
        self.assertNotEqual(self.client.session.get(SESSION_CLIENT_KEY), self.b.pk)

    def test_cliente_a_nombre_de_otro_en_el_formulario_de_documentos_se_ignora(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.admin)
        self.client.post(
            reverse("crm:cliente_documento_subir", args=[self.a.pk]),
            {"nombre": "Doc A", "tipo": "otro", "cliente": self.b.pk, "archivo": SimpleUploadedFile("a.pdf", b"a")},
        )
        doc = DocumentoCliente.all_objects.get(nombre="Doc A")
        self.assertEqual(doc.cliente_id, self.a.pk)


class CapaDeDatosTests(BaseAislamiento):
    """Aislamiento en el modelo: aunque una vista se equivoque, la consulta no devuelve datos ajenos."""

    def test_el_manager_solo_devuelve_documentos_de_clientes_permitidos(self):
        self._restringir({self.a.pk})
        nombres = set(DocumentoCliente.objects.values_list("nombre", flat=True))
        self.assertEqual(nombres, {"Contrato Alfa"})

    def test_sin_clientes_permitidos_no_se_ve_nada(self):
        self._restringir(set())
        self.assertEqual(DocumentoCliente.objects.count(), 0)

    def test_no_se_guarda_un_documento_en_un_cliente_ajeno(self):
        self._restringir({self.a.pk})
        with self.assertRaises(PermissionDenied):
            DocumentoCliente(cliente=self.b, nombre="Intruso", archivo=ContentFile(b"x", name="i.pdf")).save()
        self.assertEqual(DocumentoCliente.all_objects.filter(nombre="Intruso").count(), 0)

    def test_el_contexto_se_limpia_entre_peticiones(self):
        """Un usuario de cliente no hereda el alcance de la petición anterior."""
        self.client.force_login(self.admin)
        self.client.get(reverse("crm:clientes"))
        self.assertIsNone(get_allowed_client_ids())


class AislamientoDeKPIsTests(BaseAislamiento):
    """Los KPIs y sus mediciones también quedan aislados por cliente."""

    def setUp(self):
        super().setUp()
        from apps.clients.models import KPICliente, MedicionKPI

        self.kpi_a = KPICliente.all_objects.create(cliente=self.a, indicador="seguidores", valor_inicial=100, meta=200)
        self.kpi_b = KPICliente.all_objects.create(cliente=self.b, indicador="seguidores", valor_inicial=7777, meta=9999)
        MedicionKPI.all_objects.create(cliente=self.b, kpi=self.kpi_b, fecha="2026-10-01", valor=8888)

    def test_ficha_propia_no_muestra_kpis_del_otro_cliente(self):
        self.client.force_login(self.colab)
        r = self.client.get(reverse("crm:cliente_ficha", args=[self.a.pk]))
        self.assertContains(r, "Seguidores")
        for secreto in ("7777", "9999", "8888"):
            self.assertNotContains(r, secreto)

    def test_no_se_mide_ni_se_elimina_un_kpi_ajeno(self):
        from apps.clients.models import KPICliente, MedicionKPI

        self.client.force_login(self.admin)
        antes = MedicionKPI.all_objects.count()
        # KPI de B pedido a través de la URL del cliente A: no existe para A
        r1 = self.client.post(reverse("crm:cliente_kpi_medicion", args=[self.a.pk, self.kpi_b.pk]), {"fecha": "2026-10-02", "valor": "1"})
        r2 = self.client.post(reverse("crm:cliente_kpi_eliminar", args=[self.a.pk, self.kpi_b.pk]))
        self.assertEqual((r1.status_code, r2.status_code), (404, 404))
        self.assertEqual(MedicionKPI.all_objects.count(), antes)
        self.assertTrue(KPICliente.all_objects.filter(pk=self.kpi_b.pk).exists())

    def test_colaboradora_no_toca_kpis_de_cliente_no_asignado(self):
        self.client.force_login(self.colab)
        for nombre, args in (("crm:cliente_kpi_crear", [self.b.pk]), ("crm:cliente_kpi_medicion", [self.b.pk, self.kpi_b.pk]), ("crm:cliente_kpi_eliminar", [self.b.pk, self.kpi_b.pk])):
            with self.subTest(vista=nombre):
                self.assertEqual(self.client.post(reverse(nombre, args=args), {}).status_code, 404)

    def test_el_manager_filtra_kpis_y_mediciones_por_cliente(self):
        from apps.clients.models import KPICliente, MedicionKPI

        self._restringir({self.a.pk})
        self.assertEqual(set(KPICliente.objects.values_list("cliente_id", flat=True)), {self.a.pk})
        self.assertEqual(MedicionKPI.objects.count(), 0)

    def test_no_se_guarda_un_kpi_en_un_cliente_ajeno(self):
        from apps.clients.models import KPICliente

        self._restringir({self.a.pk})
        with self.assertRaises(PermissionDenied):
            KPICliente(cliente=self.b, indicador="alcance", valor_inicial=1, meta=2).save()
