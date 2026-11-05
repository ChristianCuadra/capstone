"""Revisión de seguridad y protección de datos (Ley 21.719): login, 2FA del equipo, admin, auditoría y derechos."""

from allauth.mfa.models import Authenticator
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Rol
from apps.clients.models import Cliente
from apps.core.models import RegistroAuditoria
from apps.crm.models import Interaccion, Prospecto

User = get_user_model()
CLAVE = "Cosmo-Segura-2026"


def crear_prospecto(**extra):
    datos = dict(
        nombre="Bea Soto", empresa="Tienda Bea", correo="bea@tiendabea.cl", telefono="+56 9 1111 2222",
        rubro="Retail y moda", region="Valparaíso", tamano="solo", agencia_actual="no", presupuesto="150_250",
        instagram="@tiendabea", situacion_actual="Vendemos poco. Escríbeme a bea@tiendabea.cl",
    )
    datos.update(extra)
    return Prospecto.objects.create(**datos)


class BaseSeguridad(TestCase):
    def setUp(self):
        cache.clear()
        self.cliente = Cliente.objects.create(nombre="Panadería Alfa")
        self.admin = User.objects.create_user("adm", "adm@x.cl", CLAVE, rol=Rol.ADMINISTRADORA, is_staff=True)
        self.colab = User.objects.create_user("col", "col@x.cl", CLAVE, rol=Rol.COLABORADORA, is_staff=True)
        self.colab.clientes_asignados.set([self.cliente])
        self.aprobador = User.objects.create_user("apr", "apr@x.cl", CLAVE, rol=Rol.CLIENTE_APROBADOR, cliente=self.cliente)


class InicioDeSesionTests(BaseSeguridad):
    """El login de allauth (actualizado a 65.21) sigue funcionando y cada rol llega a su vista."""

    def _entrar(self, correo, clave=CLAVE):
        return self.client.post(reverse("account_login"), {"login": correo, "password": clave})

    def test_equipo_entra_al_panel_y_cliente_al_portal(self):
        self.assertRedirects(self._entrar("adm@x.cl"), reverse("crm:dashboard"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("crm:dashboard")).status_code, 200)
        self.client.logout()
        self.assertRedirects(self._entrar("apr@x.cl"), reverse("content:calendario"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("content:calendario")).status_code, 200)

    def test_inicios_de_sesion_quedan_en_la_auditoria_sin_la_clave(self):
        self._entrar("adm@x.cl")
        self.client.logout()
        self._entrar("adm@x.cl", "clave-equivocada")
        exito = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.INICIO_SESION)
        self.assertEqual(exito.usuario, self.admin)
        fallido = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.SESION_FALLIDA)
        self.assertIn("adm@x.cl", fallido.detalle)
        self.assertNotIn("clave-equivocada", fallido.detalle)

    def test_cuenta_desactivada_no_entra(self):
        self.colab.is_active = False
        self.colab.save()
        self._entrar("col@x.cl")
        self.assertEqual(self.client.get(reverse("crm:dashboard")).status_code, 302)


class AdminDeDjangoTests(BaseSeguridad):
    """/admin/ ya no tiene login propio: se entra por allauth (2FA, límite de intentos, auditoría)."""

    def test_sin_sesion_lleva_al_login_de_allauth(self):
        respuesta = self.client.get(reverse("admin:login"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta["Location"].startswith(reverse("account_login")))

    def test_no_acepta_contrasenas_por_el_formulario_del_admin(self):
        superusuario = User.objects.create_superuser("root", "root@x.cl", CLAVE)
        self.client.post(reverse("admin:login"), {"username": "root", "password": CLAVE})
        self.assertNotIn("_auth_user_id", self.client.session)
        # Ni siquiera con otra sesión ya iniciada (p. ej. un cliente) se cambia de cuenta por ahí.
        self.client.force_login(self.aprobador)
        self.client.post(reverse("admin:login"), {"username": "root", "password": CLAVE})
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.aprobador.pk)
        self.assertNotEqual(int(self.client.session["_auth_user_id"]), superusuario.pk)

    def test_con_sesion_y_permiso_entra_al_admin(self):
        self.client.force_login(User.objects.create_superuser("root", "root@x.cl", CLAVE))
        self.assertRedirects(self.client.get(reverse("admin:login")), reverse("admin:index"))


@override_settings(EXIGIR_2FA_EQUIPO=True)
class DosFactoresObligatorioTests(BaseSeguridad):
    def _activar_totp(self, usuario):
        Authenticator.objects.create(user=usuario, type=Authenticator.Type.TOTP, data={"secret": "JBSWY3DPEHPK3PXP"})

    def test_equipo_sin_2fa_debe_configurarlo_antes_de_entrar(self):
        for usuario in (self.admin, self.colab):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                for ruta in (reverse("crm:dashboard"), reverse("content:interna_calendario"), reverse("admin:index")):
                    self.assertRedirects(self.client.get(ruta), reverse("mfa_activate_totp"), fetch_redirect_response=False)
                self.client.logout()

    def test_el_equipo_puede_configurar_el_2fa_sin_quedar_atrapado(self):
        """Flujo real: login → panel → configurar 2FA (allauth pide confirmar la contraseña) → código QR."""
        self.client.post(reverse("account_login"), {"login": "col@x.cl", "password": CLAVE})
        self.assertRedirects(self.client.get(reverse("crm:dashboard")), reverse("mfa_activate_totp"), fetch_redirect_response=False)
        confirmar = self.client.get(reverse("mfa_activate_totp"), follow=True)
        self.assertEqual(confirmar.status_code, 200)
        self.client.post(confirmar.redirect_chain[-1][0].split("?")[0], {"password": CLAVE})
        activar = self.client.get(reverse("mfa_activate_totp"))
        self.assertEqual(activar.status_code, 200)
        self.assertContains(activar, "svg")  # el código QR para la app autenticadora
        self.assertEqual(self.client.post(reverse("account_logout")).status_code, 302)

    def test_desde_las_paginas_de_cuenta_siempre_se_puede_volver_al_inicio(self):
        """Quien no quiere escanear el QR (o ingresar el código) tiene cómo salir, sin quedar dando vueltas."""
        boton = f'href="{reverse("website:home")}" class="inline-flex'
        self.assertContains(self.client.get(reverse("account_login")), boton)
        self.client.post(reverse("account_login"), {"login": "col@x.cl", "password": CLAVE})
        confirmar = self.client.get(reverse("mfa_activate_totp"), follow=True)
        self.assertContains(confirmar, boton)
        self.client.post(confirmar.redirect_chain[-1][0].split("?")[0], {"password": CLAVE})
        activar = self.client.get(reverse("mfa_activate_totp"))
        self.assertContains(activar, boton)
        self.assertContains(activar, "Volver al inicio")
        # Sin 2FA el panel lo devuelve aquí: no se le ofrece «Ir al panel».
        self.assertNotContains(activar, "Ir al panel")
        self.assertEqual(self.client.get(reverse("website:home")).status_code, 200)

    def test_quien_deja_el_2fa_a_medias_puede_cerrar_sesion(self):
        """Volvió al inicio sin escanear el QR: la sesión sigue abierta, así que debe poder cerrarla desde ahí."""
        salir = f'action="{reverse("account_logout")}"'
        self.client.post(reverse("account_login"), {"login": "col@x.cl", "password": CLAVE})
        self.assertContains(self.client.get(reverse("mfa_activate_totp"), follow=True), salir)
        inicio = self.client.get(reverse("website:home"))
        self.assertContains(inicio, salir, count=2)  # cabecera de escritorio y menú del celular
        self.assertContains(inicio, "Cerrar sesión")
        self.assertRedirects(self.client.post(reverse("account_logout")), reverse("website:home"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotContains(self.client.get(reverse("website:home")), salir)

    def test_con_2fa_activo_tambien_puede_ir_al_panel(self):
        self._activar_totp(self.colab)
        self.client.force_login(self.colab)
        self.assertContains(self.client.get(reverse("mfa_index")), "Ir al panel")

    def test_equipo_con_2fa_entra_normal(self):
        self._activar_totp(self.colab)
        self.client.force_login(self.colab)
        self.assertEqual(self.client.get(reverse("crm:dashboard")).status_code, 200)

    def test_clientes_no_necesitan_2fa(self):
        self.client.force_login(self.aprobador)
        self.assertEqual(self.client.get(reverse("content:calendario")).status_code, 200)


class ExportacionDeProspectosTests(BaseSeguridad):
    def test_colaboradora_no_exporta_datos_personales(self):
        self.client.force_login(self.colab)
        respuesta = self.client.get(reverse("crm:prospectos_exportar"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertNotContains(self.client.get(reverse("crm:prospectos")), reverse("crm:prospectos_exportar"))

    def test_csv_neutraliza_formulas_y_queda_en_la_auditoria(self):
        crear_prospecto(empresa='=HYPERLINK("http://malo.example","clic")', nombre="+cmd", telefono="-1")
        self.client.force_login(self.admin)
        contenido = self.client.get(reverse("crm:prospectos_exportar")).content.decode("utf-8")
        self.assertIn("'=HYPERLINK", contenido)
        self.assertIn("'+cmd", contenido)
        self.assertNotIn(';=HYPERLINK', contenido)
        self.assertTrue(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.EXPORTAR, entidad="prospectos").exists())


class DerechosDeLasPersonasTests(BaseSeguridad):
    def test_descargar_los_datos_de_una_persona(self):
        prospecto = crear_prospecto()
        self.client.force_login(self.admin)
        datos = self.client.get(reverse("crm:prospecto_datos_personales", args=[prospecto.pk])).json()
        self.assertIn("bea@tiendabea.cl", str(datos["ficha"]))
        self.assertTrue(RegistroAuditoria.objects.filter(entidad="datos personales de prospecto", accion=RegistroAuditoria.Accion.EXPORTAR).exists())

    def test_anonimizar_borra_lo_que_identifica_a_la_persona(self):
        prospecto = crear_prospecto(rut="12.345.678-5")
        Interaccion.objects.create(prospecto=prospecto, tipo=Interaccion.Tipo.NOTA, titulo="Llamé a Bea Soto")
        self.client.force_login(self.admin)
        self.client.post(reverse("crm:prospecto_anonimizar", args=[prospecto.pk]))
        prospecto.refresh_from_db()
        for campo in ("nombre", "empresa", "correo", "telefono", "rut", "instagram", "situacion_actual"):
            with self.subTest(campo=campo):
                self.assertNotIn("Bea", getattr(prospecto, campo))
                self.assertNotIn("bea@", getattr(prospecto, campo))
        self.assertEqual(prospecto.rut, "")
        self.assertFalse(prospecto.interacciones.filter(titulo__icontains="Bea").exists())
        self.assertTrue(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ELIMINAR, entidad="datos personales de prospecto").exists())

    def test_colaboradora_no_anonimiza_ni_descarga(self):
        prospecto = crear_prospecto()
        self.client.force_login(self.colab)
        self.client.post(reverse("crm:prospecto_anonimizar", args=[prospecto.pk]))
        self.assertEqual(self.client.get(reverse("crm:prospecto_datos_personales", args=[prospecto.pk])).status_code, 302)
        prospecto.refresh_from_db()
        self.assertEqual(prospecto.nombre, "Bea Soto")

    def test_un_cliente_vigente_no_se_anonimiza_desde_el_prospecto(self):
        prospecto = crear_prospecto(cliente=self.cliente)
        self.client.force_login(self.admin)
        self.client.post(reverse("crm:prospecto_anonimizar", args=[prospecto.pk]))
        prospecto.refresh_from_db()
        self.assertEqual(prospecto.nombre, "Bea Soto")


class GestionDeUsuariosTests(BaseSeguridad):
    def test_administradora_no_modifica_a_un_superusuario(self):
        root = User.objects.create_superuser("root", "root@x.cl", CLAVE)
        Authenticator.objects.create(user=root, type=Authenticator.Type.TOTP, data={"secret": "JBSWY3DPEHPK3PXP"})
        self.client.force_login(self.admin)
        self.client.post(reverse("crm:usuario_editar", args=[root.pk]), {
            "username": "root", "email": "root@x.cl", "first_name": "", "last_name": "", "password": "Otra-Clave-2026", "is_active": "on",
        })
        self.client.post(reverse("crm:usuario_restablecer_2fa", args=[root.pk]))
        self.client.post(reverse("crm:usuario_alternar_activo", args=[root.pk]))
        self.client.post(reverse("crm:usuario_eliminar", args=[root.pk]))
        root.refresh_from_db()
        self.assertTrue(root.check_password(CLAVE))
        self.assertTrue(root.is_active)
        self.assertTrue(Authenticator.objects.filter(user=root).exists())

    def test_no_se_aceptan_contrasenas_debiles(self):
        from apps.accounts.forms import UsuarioForm

        form = UsuarioForm({"username": "nueva", "email": "nueva@x.cl", "first_name": "Nueva", "rol": Rol.COLABORADORA,
                            "clientes_asignados": [self.cliente.pk], "is_active": "on", "password": "123"}, es_nuevo=True)
        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)

    def test_la_agencia_no_define_contrasenas_de_clientes(self):
        from apps.accounts.forms import UsuarioForm

        nuevo = UsuarioForm({"username": "cli", "email": "cli@x.cl", "first_name": "Cli", "rol": Rol.CLIENTE_LECTOR,
                             "cliente": self.cliente.pk, "is_active": "on", "password": "Clave-Cliente-2026"}, es_nuevo=True)
        self.assertFalse(nuevo.is_valid())
        self.assertIn("rol", nuevo.errors)
        editar = UsuarioForm({"username": "apr", "email": "apr@x.cl", "first_name": "", "rol": Rol.CLIENTE_APROBADOR,
                              "cliente": self.cliente.pk, "is_active": "on", "password": "Clave-Cliente-2026"}, instance=self.aprobador)
        self.assertFalse(editar.is_valid())
        self.assertIn("password", editar.errors)


class PrivacidadYMinimizacionTests(BaseSeguridad):
    def test_politica_de_privacidad_publicada_y_enlazada(self):
        self.assertContains(self.client.get(reverse("website:privacidad")), "Tus derechos")
        for nombre in ("website:cotizacion", "website:asesoria", "website:home"):
            with self.subTest(pagina=nombre):
                self.assertContains(self.client.get(reverse(nombre)), reverse("website:privacidad"))

    def test_el_consentimiento_queda_con_su_version(self):
        from apps.website.privacidad import VERSION_POLITICA
        from apps.website.tests import DATOS_ASESORIA

        self.client.post(reverse("website:asesoria"), DATOS_ASESORIA)
        prospecto = Prospecto.objects.get()
        self.assertTrue(prospecto.interacciones.filter(descripcion__contains=f"versión {VERSION_POLITICA}").exists())

    def test_a_gemini_no_le_llegan_datos_de_contacto(self):
        from apps.ai.services import construir_prompt_diagnostico

        prompt = construir_prompt_diagnostico(crear_prospecto(situacion_actual="Llámame al +56 9 8765 4321 o a bea@tiendabea.cl. RUT 12.345.678-5"))
        for dato in ("Bea Soto", "bea@tiendabea.cl", "8765 4321", "12.345.678-5", "1111 2222"):
            self.assertNotIn(dato, prompt)


class CacheCompartidaTests(TestCase):
    def test_sin_su_tabla_usa_la_memoria_en_vez_de_fallar(self):
        from apps.core.cache import CacheBaseDatosTolerante

        CacheBaseDatosTolerante._tabla_lista = None
        cache_db = CacheBaseDatosTolerante("tabla_que_no_existe", {})
        cache_db.set("intentos", 3, 60)
        self.assertEqual(cache_db.get("intentos"), 3)
        self.assertEqual(cache_db.incr("intentos"), 4)
        CacheBaseDatosTolerante._tabla_lista = None
