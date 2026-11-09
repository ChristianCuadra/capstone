import os
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from apps.core.models import TenantModel


def ruta_pieza_contenido(instance, filename):
    return f"clientes/{instance.cliente_id}/piezas/{filename}"


def validar_extension_imagen(value):
    ext = os.path.splitext(value.name)[1].lower()
    valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.mp4', '.mov']
    if ext not in valid_extensions:
        raise ValidationError('Formato de archivo no permitido. Sube una imagen (JPG, PNG, WEBP) o video (MP4, MOV).')


class RedSocial(models.TextChoices):
    INSTAGRAM = "instagram", "Instagram"
    FACEBOOK = "facebook", "Facebook"
    LINKEDIN = "linkedin", "LinkedIn"
    TIKTOK = "tiktok", "TikTok"


class EstadoPieza(models.TextChoices):
    BORRADOR = "borrador", "Borrador"
    EN_REVISION = "en_revision", "En revisión"
    APROBADO = "aprobado", "Aprobado"
    RECHAZADO = "rechazado", "Rechazado"
    PUBLICADO = "publicado", "Publicado"


class PiezaContenido(TenantModel):
    """Pieza del calendario editorial."""

    titulo = models.CharField("título / concepto", max_length=200)
    texto = models.TextField("texto / copy", blank=True)
    red_social = models.CharField("red social", max_length=20, choices=RedSocial.choices, default=RedSocial.INSTAGRAM)
    estado = models.CharField("estado", max_length=20, choices=EstadoPieza.choices, default=EstadoPieza.BORRADOR)
    
    # Archivo multimedia
    archivo = models.FileField(
        "archivo multimedia", 
        upload_to=ruta_pieza_contenido, 
        validators=[validar_extension_imagen],
        blank=True, 
        null=True
    )
    
    # Programación
    fecha_programada = models.DateTimeField("fecha y hora programada")
    
    # Cumplimiento del plan (PC-CUM-01): qué entregable del plan es esta pieza (historia, carrusel, reel...).
    tipo_entregable = models.ForeignKey(
        "catalog.TipoEntregable",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="piezas",
        verbose_name="tipo de entregable",
    )
    # PC-IA-03 / PC-IA-04: el copy partió de un borrador generado por IA (queda identificado).
    texto_generado_ia = models.BooleanField("texto asistido por IA", default=False)

    # Versionado 
    version = models.PositiveIntegerField("versión", default=1)

    # Trazabilidad de Aprobación 
    aprobado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="piezas_aprobadas",
        verbose_name="aprobado por"
    )
    fecha_aprobacion = models.DateTimeField("fecha de aprobación", null=True, blank=True)

    # Traza
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="piezas_creadas"
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "contenido_piezas"
        verbose_name = "pieza de contenido"
        verbose_name_plural = "piezas de contenido"
        ordering = ["fecha_programada"]

    def __str__(self):
        return f"[{self.get_red_social_display()}] {self.titulo} · {self.cliente}"


class HistorialVersionPieza(models.Model):
    """Registro inmutable del historial de versiones de cada pieza."""
    pieza = models.ForeignKey(PiezaContenido, on_delete=models.CASCADE, related_name="historial_versiones")
    version = models.PositiveIntegerField()
    titulo = models.CharField(max_length=200)
    texto = models.TextField(blank=True)
    archivo = models.CharField(max_length=500, blank=True, null=True)
    estado_al_guardar = models.CharField(max_length=20)
    modificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contenido_piezas_historial"
        ordering = ["-version"]

    def __str__(self):
        return f"{self.pieza.titulo} (v{self.version})"


class ComentarioPieza(models.Model):
    """Hilo de comentarios cronológico entre cliente y agencia. """
    pieza = models.ForeignKey(PiezaContenido, on_delete=models.CASCADE, related_name="comentarios")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    comentario = models.TextField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contenido_piezas_comentarios"
        ordering = ["creado_en"]

    def __str__(self):
        return f"Comentario de {self.usuario} en {self.pieza.titulo}"

# ── Solicitudes y archivos del cliente (PC-SOL-01) ─────────────────────────

EXTENSIONES_SOLICITUD = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv",
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".zip",
}
TAMANO_MAX_SOLICITUD_MB = 20
MAX_ARCHIVOS_POR_MENSAJE = 5


def ruta_archivo_solicitud(instance, filename):
    return f"clientes/{instance.mensaje.solicitud.cliente_id}/solicitudes/{instance.mensaje.solicitud_id}/{filename}"


class Solicitud(TenantModel):
    """Pedido del cliente a la agencia desde el portal, en reemplazo de WhatsApp o el correo."""

    class Estado(models.TextChoices):
        ABIERTA = "abierta", "Abierta"
        RESPONDIDA = "respondida", "Respondida"
        CERRADA = "cerrada", "Cerrada"

    asunto = models.CharField(max_length=150)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.ABIERTA)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="solicitudes_creadas"
    )

    class Meta:
        db_table = "solicitudes"
        verbose_name = "solicitud"
        verbose_name_plural = "solicitudes"
        ordering = ["-actualizado_en"]

    def __str__(self):
        return f"{self.asunto} · {self.cliente}"


class MensajeSolicitud(models.Model):
    """Cada mensaje del hilo de una solicitud (del cliente o de la agencia)."""

    solicitud = models.ForeignKey(Solicitud, on_delete=models.CASCADE, related_name="mensajes")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    texto = models.TextField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "solicitudes_mensajes"
        ordering = ["creado_en"]

    @property
    def es_de_la_agencia(self):
        return bool(self.usuario and not self.usuario.es_cliente)


class ArchivoSolicitud(models.Model):
    mensaje = models.ForeignKey(MensajeSolicitud, on_delete=models.CASCADE, related_name="archivos")
    archivo = models.FileField(upload_to=ruta_archivo_solicitud, max_length=300)
    nombre = models.CharField(max_length=200)
    tamano = models.PositiveIntegerField("tamaño (bytes)")

    class Meta:
        db_table = "solicitudes_archivos"
        ordering = ["pk"]

    def __str__(self):
        return self.nombre
