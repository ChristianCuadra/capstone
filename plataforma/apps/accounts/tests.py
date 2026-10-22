"""Activación de cuentas de clientes (PC-AUT-07)."""

import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.clients.models import Cliente
from apps.core.models import RegistroAuditoria

from .activacion import Estado, estado_cuenta
from .models import Rol

User = get_user_model()


class ActivacionCuentaTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nombre="Café Prueba", contacto_nombre="Ana Pérez", contacto_correo="ana@cafeprueba.cl")
        self.admin = User.objects.create_user("pia", "pia@agencia.cl", "x", rol=Rol.ADMINISTRADORA, is_staff=True)
        self.url_invitar = reverse("crm:cliente_invitar", args=[self.cliente.pk])

    def invitar(self, **extra):
        datos = {"first_name": "Ana", "last_name": "Pérez", "email": "Ana@CafePrueba.cl", "rol": Rol.CLIENTE_APROBADOR}
        datos.update(extra)
        self.client.force_login(self.admin)
        return self.client.post(self.url_invitar, datos)

    def enlace_del_correo(self, indice=-1):
        return re.search(r"http://testserver(/accounts/activar/\S+/)", mail.outbox[indice].body).group(1)

    def test_ficha_muestra_acceso_al_portal_con_el_contacto_propuesto(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("crm:cliente_ficha", args=[self.cliente.pk]))
        self.assertContains(respuesta, "Acceso al portal")
        self.assertContains(respuesta, 'value="ana@cafeprueba.cl"')

    def test_invitar_crea_cuenta_pendiente_y_envia_correo(self):
        self.invitar()
        usuario = User.objects.get(email="ana@cafeprueba.cl")
        self.assertEqual(usuario.cliente, self.cliente)
        self.assertEqual(usuario.rol, Rol.CLIENTE_APROBADOR)
        self.assertFalse(usuario.is_staff)
        self.assertFalse(usuario.has_usable_password())
        self.assertEqual(estado_cuenta(usuario), Estado.PENDIENTE)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ana@cafeprueba.cl"])
        self.assertIn("/accounts/activar/", mail.outbox[0].body)
        self.assertTrue(RegistroAuditoria.objects.filter(entidad="usuario", entidad_id=str(usuario.pk), accion="crear").exists())
        ficha = self.client.get(reverse("crm:cliente_ficha", args=[self.cliente.pk]))
        self.assertContains(ficha, "Pendiente de activación")
        self.assertContains(ficha, "Copiar enlace de activación")

    def test_cuenta_pendiente_no_puede_iniciar_sesion(self):
        self.invitar()
        self.client.logout()
        self.assertFalse(self.client.login(username="ana", password=""))

    def test_correo_duplicado_no_crea_otra_cuenta(self):
        self.invitar()
        self.invitar(email="ana@cafeprueba.cl")
        self.assertEqual(User.objects.filter(email="ana@cafeprueba.cl").count(), 1)

    def test_solo_la_administradora_puede_invitar(self):
        colaboradora = User.objects.create_user("cata", "cata@agencia.cl", "x", rol=Rol.COLABORADORA, is_staff=True)
        colaboradora.clientes_asignados.add(self.cliente)
        self.client.force_login(colaboradora)
        self.client.post(self.url_invitar, {"first_name": "Ana", "email": "ana@cafeprueba.cl", "rol": Rol.CLIENTE_LECTOR})
        self.assertFalse(User.objects.filter(email="ana@cafeprueba.cl").exists())
        ficha = self.client.get(reverse("crm:cliente_ficha", args=[self.cliente.pk]))
        self.assertNotContains(ficha, "Acceso al portal")

    def test_cliente_inactivo_no_recibe_invitacion(self):
        self.cliente.activo = False
        self.cliente.save()
        self.invitar()
        self.assertFalse(User.objects.filter(email="ana@cafeprueba.cl").exists())

    def test_activar_define_contrasena_entra_al_portal_y_el_enlace_no_se_reutiliza(self):
        self.invitar()
        enlace = self.enlace_del_correo()
        self.client.logout()

        pagina = self.client.get(enlace)
        self.assertContains(pagina, "Activa tu cuenta")
        self.assertContains(pagina, "Café Prueba")

        respuesta = self.client.post(enlace, {"new_password1": "Cosmo-Portal-2026", "new_password2": "Cosmo-Portal-2026"})
        self.assertRedirects(respuesta, reverse("content:calendario"), fetch_redirect_response=False)
        usuario = User.objects.get(email="ana@cafeprueba.cl")
        self.assertTrue(usuario.check_password("Cosmo-Portal-2026"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), usuario.pk)
        self.assertEqual(estado_cuenta(usuario), Estado.ACTIVA)

        self.client.logout()
        self.assertEqual(self.client.get(enlace).status_code, 400)

    def test_contrasena_debil_se_rechaza(self):
        self.invitar()
        enlace = self.enlace_del_correo()
        self.client.logout()
        respuesta = self.client.post(enlace, {"new_password1": "12345678", "new_password2": "12345678"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(User.objects.get(email="ana@cafeprueba.cl").has_usable_password())

    def test_enlace_alterado_no_sirve(self):
        respuesta = self.client.get(reverse("cuenta_activar", args=["MQ", "token-falso"]))
        self.assertContains(respuesta, "Este enlace ya no es válido", status_code=400)

    def test_reenviar_invitacion_manda_otro_correo(self):
        self.invitar()
        usuario = User.objects.get(email="ana@cafeprueba.cl")
        self.client.post(reverse("crm:cliente_reenviar_invitacion", args=[self.cliente.pk, usuario.pk]))
        self.assertEqual(len(mail.outbox), 2)

    def test_si_el_correo_falla_la_cuenta_igual_queda_creada(self):
        with self.settings(EMAIL_BACKEND="apps.accounts.tests.BackendQueFalla"):
            respuesta = self.invitar()
        self.assertTrue(User.objects.filter(email="ana@cafeprueba.cl").exists())
        mensajes = [str(m) for m in respuesta.wsgi_request._messages]
        self.assertTrue(any("no se pudo enviar el correo" in m for m in mensajes))


class BackendQueFalla:
    def __init__(self, *args, **kwargs):
        pass

    def send_messages(self, mensajes):
        raise OSError("sin servidor de correo")
