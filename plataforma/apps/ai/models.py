from django.conf import settings
from django.db import models


class RegistroIA(models.Model):
    """Cada invocación al modelo de lenguaje, para auditoría y control de costo (Documento de Alcance 6.4)."""

    class Tipo(models.TextChoices):
        DIAGNOSTICO_COTIZACION = "diagnostico_cotizacion", "Diagnóstico de cotización"
        REPORTE_MENSUAL = "reporte_mensual", "Reporte mensual"
        COPY = "copy", "Copy con voz de marca"

    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    proveedor = models.CharField(max_length=30, default="gemini")
    modelo = models.CharField(max_length=60)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    prospecto = models.ForeignKey("crm.Prospecto", null=True, blank=True, on_delete=models.SET_NULL, related_name="registros_ia")
    tokens_entrada = models.PositiveIntegerField(null=True, blank=True)
    tokens_salida = models.PositiveIntegerField(null=True, blank=True)
    duracion_ms = models.PositiveIntegerField(null=True, blank=True)
    exitoso = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "registros_ia"
        verbose_name = "registro de IA"
        verbose_name_plural = "registros de IA"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.modelo} · {'ok' if self.exitoso else 'error'}"
