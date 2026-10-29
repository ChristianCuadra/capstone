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