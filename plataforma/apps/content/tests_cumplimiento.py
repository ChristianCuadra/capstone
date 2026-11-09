from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Rol
from apps.catalog.models import Plan, PlanEntregable, TipoEntregable
from apps.clients.models import Cliente

from .cumplimiento import cumplimiento_cliente
from .models import EstadoPieza, PiezaContenido


def _fecha(d, hora=10):
    return timezone.make_aware(datetime(d.year, d.month, d.day, hora, 0))


class CumplimientoTests(TestCase):
    """PC-CUM-01 y PC-CUM-02 · Cumplimiento del plan (agencia y cliente)."""

    def setUp(self):
        User = get_user_model()
        self.historia = TipoEntregable.objects.create(nombre="Historia T", nombre_plural="historias", slug="historia-t", tiene_cuota=True)
        self.reel = TipoEntregable.objects.create(nombre="Reel T", nombre_plural="reels", slug="reel-t", tiene_cuota=True)
        self.branding = TipoEntregable.objects.create(nombre="Branding T", slug="branding-t", tiene_cuota=False)
        self.plan = Plan.objects.create(nombre="Plan T", slug="plan-t", precio_mensual=100000)
        PlanEntregable.objects.create(plan=self.plan, tipo_entregable=self.historia, cantidad_mensual=4)
        PlanEntregable.objects.create(plan=self.plan, tipo_entregable=self.reel, cantidad_mensual=2)
        PlanEntregable.objects.create(plan=self.plan, tipo_entregable=self.branding)
        self.a = Cliente.objects.create(nombre="Alfa", plan=self.plan)
        self.b = Cliente.objects.create(nombre="Beta", plan=self.plan)
        self.admin = User.objects.create_user("adm", "adm@x.cl", "x", rol=Rol.ADMINISTRADORA, is_staff=True)
        self.colab_b = User.objects.create_user("cb", "cb@x.cl", "x", rol=Rol.COLABORADORA, is_staff=True)
        self.colab_b.clientes_asignados.set([self.b])
        self.lec_a = User.objects.create_user("lea", "lea@x.cl", "x", rol=Rol.CLIENTE_LECTOR, cliente=self.a)
        self.mes = date(2026, 11, 1)

    def _pieza(self, tipo, estado, dia=5, cliente=None):
        return PiezaContenido.all_objects.create(
            cliente=cliente or self.a, titulo=f"{tipo} {estado}", tipo_entregable=tipo, estado=estado,
            fecha_programada=_fecha(self.mes.replace(day=dia)),
        )

    def test_cuenta_comprometido_entregado_y_aprobado_por_tipo(self):
        self._pieza(self.historia, EstadoPieza.EN_REVISION)
        self._pieza(self.historia, EstadoPieza.APROBADO)
        self._pieza(self.historia, EstadoPieza.PUBLICADO)
        self._pieza(self.historia, EstadoPieza.BORRADOR)  # programada, no entregada
        self._pieza(self.historia, EstadoPieza.RECHAZADO)  # no cuenta
        self._pieza(self.reel, EstadoPieza.APROBADO)
        c = cumplimiento_cliente(self.a, self.mes, hoy=date(2026, 11, 10))
        historias = next(f for f in c["filas"] if f["tipo"] == "Historias")
        self.assertEqual((historias["comprometido"], historias["programado"], historias["entregado"], historias["aprobado"]), (4, 4, 3, 2))
        self.assertEqual(len(c["filas"]), 2, "Branding no tiene cuota y no se mide")
        self.assertEqual((c["comprometido"], c["entregado"], c["aprobado"]), (6, 4, 3))

    def test_estados_cumplido_en_riesgo_e_incumplido(self):
        for _ in range(4):
            self._pieza(self.historia, EstadoPieza.APROBADO)
        self._pieza(self.reel, EstadoPieza.EN_REVISION)
        # Mes en curso: historias cumplidas; reels con 1 de 2 programados -> en riesgo.
        c = cumplimiento_cliente(self.a, self.mes, hoy=date(2026, 11, 10))
        estados = {f["tipo"]: f["estado"] for f in c["filas"]}
        self.assertEqual(estados, {"Historias": "cumplido", "Reels": "en_riesgo"})
        self.assertTrue(c["en_riesgo"])
        # Mes terminado: lo que no se alcanzó queda incumplido.
        c = cumplimiento_cliente(self.a, self.mes, hoy=date(2026, 12, 2))
        self.assertEqual({f["tipo"]: f["estado"] for f in c["filas"]}["Reels"], "incumplido")

    def test_al_dia_si_esta_programado_y_va_al_ritmo(self):
        for estado in (EstadoPieza.APROBADO, EstadoPieza.BORRADOR, EstadoPieza.BORRADOR, EstadoPieza.BORRADOR):
            self._pieza(self.historia, estado)
        self._pieza(self.reel, EstadoPieza.BORRADOR)
        self._pieza(self.reel, EstadoPieza.BORRADOR)
        c = cumplimiento_cliente(self.a, self.mes, hoy=date(2026, 11, 3))
        self.assertEqual({f["estado"] for f in c["filas"]}, {"al_dia"})

    def test_piezas_sin_tipo_se_informan(self):
        self._pieza(None, EstadoPieza.EN_REVISION)
        self.assertEqual(cumplimiento_cliente(self.a, self.mes, hoy=date(2026, 11, 10))["sin_tipo"], 1)

    def test_cliente_sin_plan(self):
        sin_plan = Cliente.objects.create(nombre="Gamma")
        c = cumplimiento_cliente(sin_plan, self.mes)
        self.assertEqual((c["filas"], c["estado"]), ([], "sin_plan"))

    def test_pantalla_de_la_agencia_destaca_en_riesgo_y_respeta_aislamiento(self):
        self._pieza(self.historia, EstadoPieza.APROBADO, cliente=self.b)
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("content:panel_cumplimiento"), {"mes": "2026-11"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Alfa")
        self.assertContains(respuesta, "Beta")
        self.client.force_login(self.colab_b)
        respuesta = self.client.get(reverse("content:panel_cumplimiento"), {"mes": "2026-11"})
        self.assertNotContains(respuesta, "Alfa")
        self.assertContains(respuesta, "Beta")

    def test_cliente_no_entra_a_la_pantalla_de_la_agencia(self):
        self.client.force_login(self.lec_a)
        self.assertEqual(self.client.get(reverse("content:panel_cumplimiento")).status_code, 302)

    def test_portal_muestra_los_mismos_numeros_que_la_agencia(self):
        self._pieza(self.historia, EstadoPieza.APROBADO)
        self._pieza(self.historia, EstadoPieza.EN_REVISION)
        self._pieza(self.reel, EstadoPieza.APROBADO, cliente=self.b)  # de otro cliente: no debe contar
        self.client.force_login(self.lec_a)
        portal = self.client.get(reverse("content:calendario"), {"mes": "2026-11"}).context["cumplimiento"]
        self.client.force_login(self.admin)
        panel = self.client.get(reverse("content:panel_cumplimiento"), {"mes": "2026-11"}).context["datos"]
        agencia = next(d for d in panel if d["cliente"] == self.a)
        self.assertEqual(
            [(f["tipo"], f["comprometido"], f["entregado"], f["aprobado"]) for f in portal["filas"]],
            [(f["tipo"], f["comprometido"], f["entregado"], f["aprobado"]) for f in agencia["filas"]],
        )
        self.assertEqual((portal["entregado"], portal["aprobado"]), (2, 1))

    def test_crear_pieza_con_tipo_de_entregable(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("content:crear_pieza"), {
            "cliente_id": self.a.pk, "titulo": "Historia 1", "red_social": "instagram", "tipo_entregable": self.historia.pk,
            "fecha_programada": "2026-11-20T10:00", "estado": "borrador", "texto": "", "texto_generado_ia": "True",
        })
        pieza = PiezaContenido.all_objects.get(titulo="Historia 1")
        self.assertEqual(pieza.tipo_entregable, self.historia)
        self.assertTrue(pieza.texto_generado_ia)


class CopyIATests(TestCase):
    """PC-IA-03 · Copy con voz de marca (y PC-IA-04: solo rellena el formulario, no guarda ni envía)."""

    def setUp(self):
        User = get_user_model()
        self.a = Cliente.objects.create(nombre="Alfa", directrices_marca="Tono alegre y cercano")
        self.b = Cliente.objects.create(nombre="Beta")
        self.colab_a = User.objects.create_user("ca", "ca@x.cl", "x", rol=Rol.COLABORADORA, is_staff=True)
        self.colab_a.clientes_asignados.set([self.a])
        self.lec_a = User.objects.create_user("lea", "lea@x.cl", "x", rol=Rol.CLIENTE_LECTOR, cliente=self.a)

    def _post(self, cliente):
        return self.client.post(reverse("content:copy_ia"), {"cliente_id": cliente.pk, "titulo": "Lanzamiento", "red_social": "instagram"})

    def test_sin_clave_responde_error_claro(self):
        self.client.force_login(self.colab_a)
        respuesta = self._post(self.a)
        self.assertEqual(respuesta.status_code, 503)
        self.assertIn("no está configurada", respuesta.json()["error"])

    def test_genera_con_la_voz_de_marca_y_no_crea_piezas(self):
        from unittest import mock

        from django.test import override_settings

        self.client.force_login(self.colab_a)
        with override_settings(AI_API_KEY="clave"), mock.patch(
            "apps.ai.services._llamar_modelo", return_value=("¡Llegó lo nuevo! #alfa", 5, 5, "gemini", "m")
        ) as llamada:
            respuesta = self._post(self.a)
        self.assertEqual(respuesta.json()["texto"], "¡Llegó lo nuevo! #alfa")
        self.assertIn("Tono alegre y cercano", llamada.call_args.args[1])
        self.assertFalse(PiezaContenido.all_objects.exists())

    def test_colaboradora_no_genera_para_cliente_no_asignado(self):
        self.client.force_login(self.colab_a)
        self.assertEqual(self._post(self.b).status_code, 400)

    def test_cliente_no_usa_la_ia_del_panel(self):
        self.client.force_login(self.lec_a)
        self.assertEqual(self._post(self.a).status_code, 302)
