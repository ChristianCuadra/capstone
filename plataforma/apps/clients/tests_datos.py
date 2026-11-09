from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Rol
from apps.clients.models import Cliente, DocumentoCliente
from apps.content.models import ComentarioPieza, EstadoPieza, PiezaContenido, Solicitud
from apps.core.models import RegistroAuditoria
from apps.crm.models import Prospecto
from apps.metrics.models import Fuente, MetricaDiaria
from apps.reports.models import ReporteMensual


class DatosPersonalesClienteTests(TestCase):
    """Ley 21.719 en la ficha del cliente: acceso (PDF), portabilidad (JSON) y supresión (anonimizar)."""

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user("adm", "adm@x.cl", "x", rol=Rol.ADMINISTRADORA, is_staff=True)
        self.colab = User.objects.create_user("col", "col@x.cl", "x", rol=Rol.COLABORADORA, is_staff=True)
        self.cliente = Cliente.objects.create(nombre="Café Ñuñoa", rut="11.111.111-1", contacto_correo="ana@cafe.cl", rubro="Gastronomía")
        self.colab.clientes_asignados.set([self.cliente])
        self.prospecto = Prospecto.objects.create(nombre="Ana Pérez", empresa="Café Ñuñoa", correo="ana@cafe.cl", cliente=self.cliente)
        self.usuario = User.objects.create_user("ana", "ana@cafe.cl", "x", rol=Rol.CLIENTE_APROBADOR, cliente=self.cliente)
        DocumentoCliente.all_objects.create(cliente=self.cliente, nombre="Contrato", archivo=SimpleUploadedFile("c.pdf", b"x"))
        s = Solicitud.all_objects.create(cliente=self.cliente, asunto="Logo nuevo", creado_por=self.usuario)
        s.mensajes.create(usuario=self.usuario, texto="Adjunto el logo")
        self.pieza = PiezaContenido.all_objects.create(cliente=self.cliente, titulo="Lanzamiento Café Ñuñoa", texto="Copy", estado=EstadoPieza.APROBADO, fecha_programada=timezone.now())
        ComentarioPieza.objects.create(pieza=self.pieza, usuario=self.usuario, comentario="Me gusta")
        ReporteMensual.all_objects.create(cliente=self.cliente, mes=date(2026, 10, 1), contenido="Reporte de Café Ñuñoa")
        MetricaDiaria.all_objects.create(cliente=self.cliente, fecha=date(2026, 10, 1), fuente=Fuente.INSTAGRAM, alcance=500)
        self.client.force_login(self.admin)

    def test_descarga_json_y_pdf(self):
        r = self.client.get(reverse("crm:cliente_datos_personales", args=[self.cliente.pk]))
        datos = r.json()
        self.assertEqual(datos["usuarios_del_portal"][0]["correo"], "ana@cafe.cl")
        self.assertEqual(datos["solicitudes"][0]["asunto"], "Logo nuevo")
        r = self.client.get(reverse("crm:cliente_datos_personales_pdf", args=[self.cliente.pk]))
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertEqual(RegistroAuditoria.objects.filter(entidad="datos personales de cliente").count(), 2)

    def test_pdf_del_prospecto(self):
        r = self.client.get(reverse("crm:prospecto_datos_personales_pdf", args=[self.prospecto.pk]))
        self.assertEqual(r["Content-Type"], "application/pdf")

    def test_colaboradora_no_descarga_ni_elimina(self):
        self.client.force_login(self.colab)
        self.assertEqual(self.client.get(reverse("crm:cliente_datos_personales", args=[self.cliente.pk])).status_code, 302)
        self.client.post(reverse("crm:cliente_anonimizar", args=[self.cliente.pk]))
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nombre, "Café Ñuñoa")

    def test_no_elimina_si_el_cliente_esta_activo(self):
        self.client.post(reverse("crm:cliente_anonimizar", args=[self.cliente.pk]))
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nombre, "Café Ñuñoa")

    def test_anonimiza_y_conserva_cifras(self):
        Cliente.objects.filter(pk=self.cliente.pk).update(activo=False)
        self.client.post(reverse("crm:cliente_anonimizar", args=[self.cliente.pk]))
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nombre, f"Cliente anonimizado #{self.cliente.pk}")
        self.assertEqual((self.cliente.rut, self.cliente.contacto_correo), ("", ""))
        self.assertEqual(self.cliente.rubro, "Gastronomía")
        self.assertFalse(get_user_model().objects.filter(username="ana").exists())
        self.assertFalse(DocumentoCliente.all_objects.filter(cliente=self.cliente).exists())
        self.assertFalse(Solicitud.all_objects.filter(cliente=self.cliente).exists())
        self.assertFalse(ReporteMensual.all_objects.filter(cliente=self.cliente).exists())
        self.pieza.refresh_from_db()
        self.assertEqual((self.pieza.titulo, self.pieza.texto, self.pieza.estado), (f"Pieza #{self.pieza.pk}", "", EstadoPieza.APROBADO))
        self.assertFalse(ComentarioPieza.objects.filter(pieza=self.pieza).exists())
        self.assertTrue(MetricaDiaria.all_objects.filter(cliente=self.cliente).exists())
        self.prospecto.refresh_from_db()
        self.assertNotIn("Ñuñoa", self.prospecto.empresa)
        self.assertTrue(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ELIMINAR, entidad="datos personales de cliente").exists())

    def test_ficha_muestra_la_seccion(self):
        r = self.client.get(reverse("crm:cliente_ficha", args=[self.cliente.pk]))
        self.assertContains(r, "Descargar sus datos (PDF)")
        self.assertContains(r, "primero desmarca")
