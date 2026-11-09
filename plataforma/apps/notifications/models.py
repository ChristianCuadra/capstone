"""Notificaciones dentro de la plataforma y correos con reintento (PC-SOL-02)."""

from django.conf import settings
from django.db import models


class Notificacion(models.Model):
    """Aviso para un usuario: se ve en la campana del panel o del portal."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notificaciones")
    titulo = models.CharField(max_length=200)
    mensaje = models.CharField(max_length=500, blank=True)
    url = models.CharField("enlace", max_length=300, blank=True)
    leida = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notificaciones"
        verbose_name = "notificación"
        verbose_name_plural = "notificaciones"
        ordering = ["-creado_en"]
        indexes = [models.Index(fields=["usuario", "leida"])]

    def __str__(self):
        return f"{self.usuario} · {self.titulo}"


class CorreoSaliente(models.Model):
    """Correo que acompaña una notificación. Si el envío falla queda pendiente y se reintenta."""

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ENVIADO = "enviado", "Enviado"
        FALLIDO = "fallido", "Fallido (sin más reintentos)"

    destinatario = models.EmailField()
    asunto = models.CharField(max_length=200)
    cuerpo = models.TextField()
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    intentos = models.PositiveSmallIntegerField(default=0)
    ultimo_error = models.CharField(max_length=300, blank=True)
    proximo_intento = models.DateTimeField(null=True, blank=True)
    enviado_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "correos_salientes"
        verbose_name = "correo saliente"
        verbose_name_plural = "correos salientes"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.destinatario} · {self.asunto} · {self.get_estado_display()}"
