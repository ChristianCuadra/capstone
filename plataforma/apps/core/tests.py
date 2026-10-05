
# Create your tests here.
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, models
from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, TransactionTestCase

from apps.clients.models import Cliente

from .access import clientes_visibles, ids_permitidos, obtener_cliente_visible
from .context import get_allowed_client_ids, get_current_client_id
from .middleware import SESSION_CLIENT_KEY, TenantMiddleware
from .models import TenantModel
from .validators import formatear_rut


class RutTests(SimpleTestCase):
    def test_rut_valido_se_normaliza(self):
        self.assertEqual(formatear_rut("123456785"), "12.345.678-5")
        self.assertEqual(formatear_rut("12.345.678-5"), "12.345.678-5")
        self.assertEqual(formatear_rut("7654321-6"), "7.654.321-6")
        self.assertEqual(formatear_rut("1.000.005-k"), "1.000.005-K")
        self.assertEqual(formatear_rut("1000013-0"), "1.000.013-0")

    def test_rut_invalido_se_rechaza(self):
        for valor in ("12.345.678-9", "abc", "1-9", "12345678", "123456789012-3"):
            with self.subTest(valor=valor):
                with self.assertRaises(ValidationError):
                    formatear_rut(valor)


class NotaDePrueba(TenantModel):
    """Entidad mínima de prueba (solo existe durante los tests) para probar el aislamiento."""

    texto = models.CharField(max_length=50)

    class Meta:
        app_label = "core"


class AislamientoTests(TransactionTestCase):
    """PC-AUT-04, PC-AUT-05 y base de PC-TEC-04: nadie ve ni toca datos de un cliente que no le corresponde."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.schema_editor() as editor:
            editor.create_model(NotaDePrueba)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as editor:
            editor.delete_model(NotaDePrueba)
        super().tearDownClass()

    def setUp(self):
        User = get_user_model()
        self.a = Cliente.objects.create(nombre="Cliente A")
        self.b = Cliente.objects.create(nombre="Cliente B")
        self.c = Cliente.objects.create(nombre="Cliente C")
        for cliente in (self.a, self.b, self.c):
            NotaDePrueba.all_objects.create(cliente=cliente, texto=f"nota de {cliente.nombre}")
        self.admin = User.objects.create_user("adm", "adm@x.cl", "x", rol="administradora", is_staff=True)
        self.colab = User.objects.create_user("col", "col@x.cl", "x", rol="colaboradora", is_staff=True)
        self.colab.clientes_asignados.set([self.a, self.b])
        self.cli_a = User.objects.create_user("cla", "cla@x.cl", "x", rol="cliente_aprobador", cliente=self.a)
        self.sin_rol = User.objects.create_user("sr", "sr@x.cl", "x")
        self.sin_cliente = User.objects.create_user("sc", "sc@x.cl", "x", rol="cliente_lector")

    def _peticion(self, usuario, **sesion):
        """Corre la petición por el middleware y devuelve lo que ve el modelo dentro de la vista."""
        request = RequestFactory().get("/")
        request.user = usuario
        request.session = dict(sesion)
        visto = {}

        def vista(req):
            visto["textos"] = sorted(NotaDePrueba.objects.values_list("texto", flat=True))
            visto["activo"] = get_current_client_id()
            visto["permitidos"] = get_allowed_client_ids()
            from django.http import HttpResponse
            return HttpResponse("ok")

        TenantMiddleware(vista)(request)
        return visto, request

    def test_cliente_solo_ve_su_empresa(self):
        visto, _ = self._peticion(self.cli_a)
        self.assertEqual(visto["textos"], ["nota de Cliente A"])
        self.assertEqual(visto["activo"], self.a.pk)

    def test_cliente_no_puede_cambiar_de_empresa_manipulando_la_sesion(self):
        visto, _ = self._peticion(self.cli_a, **{SESSION_CLIENT_KEY: self.b.pk})
        self.assertEqual(visto["textos"], ["nota de Cliente A"])
        self.assertEqual(visto["activo"], self.a.pk)

    def test_cliente_sin_empresa_no_ve_nada(self):
        visto, _ = self._peticion(self.sin_cliente)
        self.assertEqual(visto["textos"], [])

    def test_colaboradora_sin_seleccion_ve_solo_sus_clientes(self):
        visto, _ = self._peticion(self.colab)
        self.assertEqual(visto["textos"], ["nota de Cliente A", "nota de Cliente B"])
        self.assertIsNone(visto["activo"])

    def test_colaboradora_con_cliente_activo_ve_solo_ese(self):
        visto, _ = self._peticion(self.colab, **{SESSION_CLIENT_KEY: self.b.pk})
        self.assertEqual(visto["textos"], ["nota de Cliente B"])

    def test_colaboradora_con_cliente_no_asignado_en_sesion_se_ignora_y_se_descarta(self):
        visto, request = self._peticion(self.colab, **{SESSION_CLIENT_KEY: self.c.pk})
        self.assertEqual(visto["textos"], ["nota de Cliente A", "nota de Cliente B"])
        self.assertIsNone(visto["activo"])
        self.assertNotIn(SESSION_CLIENT_KEY, request.session)

    def test_al_quitarle_un_cliente_deja_de_verlo_de_inmediato(self):
        self.colab.clientes_asignados.remove(self.b)
        visto, _ = self._peticion(self.colab, **{SESSION_CLIENT_KEY: self.b.pk})
        self.assertEqual(visto["textos"], ["nota de Cliente A"])
        self.assertIsNone(visto["activo"])

    def test_administradora_ve_todo_y_puede_elegir_un_cliente(self):
        visto, _ = self._peticion(self.admin)
        self.assertEqual(len(visto["textos"]), 3)
        visto, _ = self._peticion(self.admin, **{SESSION_CLIENT_KEY: self.c.pk})
        self.assertEqual(visto["textos"], ["nota de Cliente C"])

    def test_usuario_sin_rol_ni_equipo_y_sesion_anonima_no_ven_nada(self):
        visto, _ = self._peticion(self.sin_rol)
        self.assertEqual(visto["textos"], [])
        from django.contrib.auth.models import AnonymousUser
        visto, _ = self._peticion(AnonymousUser())
        self.assertEqual(visto["textos"], [])

    def test_fuera_de_una_peticion_no_se_filtra(self):
        self.assertEqual(NotaDePrueba.objects.count(), 3)

    def test_no_se_puede_guardar_en_un_cliente_ajeno(self):
        from .context import reset_allowed_client_ids, set_allowed_client_ids

        token = set_allowed_client_ids({self.a.pk})
        try:
            with self.assertRaises(PermissionDenied):
                NotaDePrueba(cliente=self.b, texto="intruso").save()
            NotaDePrueba(cliente=self.a, texto="propia").save()
        finally:
            reset_allowed_client_ids(token)

    def test_clientes_visibles_y_acceso_por_id(self):
        self.assertEqual(set(clientes_visibles(self.colab)), {self.a, self.b})
        self.assertEqual(set(clientes_visibles(self.cli_a)), {self.a})
        self.assertEqual(set(clientes_visibles(self.admin)), {self.a, self.b, self.c})
        self.assertEqual(obtener_cliente_visible(self.colab, self.a.pk), self.a)
        for usuario, ajeno in ((self.colab, self.c), (self.cli_a, self.b)):
            with self.subTest(usuario=usuario.username):
                with self.assertRaises(Http404):
                    obtener_cliente_visible(usuario, ajeno.pk)
        with self.assertRaises(Http404):
            obtener_cliente_visible(self.colab, "no-es-un-id")
        self.assertIsNone(ids_permitidos(self.admin))
