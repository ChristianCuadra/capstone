import os
from django.db import models
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
    """Pieza del calendario editorial (PC-CAL-01, PC-CAL-02, PC-POR-01)."""

    titulo = models.CharField("título / concepto", max_length=200)
    texto = models.TextField("texto / copy", blank=True)
    red_social = models.CharField("red social", max_length=20, choices=RedSocial.choices, default=RedSocial.INSTAGRAM)
    estado = models.CharField("estado", max_length=20, choices=EstadoPieza.choices, default=EstadoPieza.BORRADOR)
    
    # Archivo multimedia (CP-046)
    archivo = models.FileField(
        "archivo multimedia", 
        upload_to=ruta_pieza_contenido, 
        validators=[validar_extension_imagen],
        blank=True, 
        null=True
    )
    
    # Programación
    fecha_programada = models.DateTimeField("fecha y hora programada")
    
    # Traza
    creado_por = models.ForeignKey(
        "accounts.User", 
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