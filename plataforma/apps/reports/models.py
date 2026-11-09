"""Reporte mensual del cliente (PC-IA-02) con aprobación humana (PC-IA-04) y descarga en el portal (PC-REP-01)."""

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class ReporteMensual(TenantModel):
    class Estado(models.TextChoices):
        BORRADOR = "borrador", "Borrador (solo la agencia lo ve)"
        APROBADO = "aprobado", "Aprobado (visible para el cliente)"

    mes = models.DateField(help_text="Primer día del mes que informa.")
    contenido = models.TextField(blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.BORRADOR)
    generado_con_ia = models.BooleanField("borrador generado con IA", default=False)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    aprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "reportes_mensuales"
        verbose_name = "reporte mensual"
        verbose_name_plural = "reportes mensuales"
        ordering = ["-mes"]
        constraints = [models.UniqueConstraint(fields=["cliente", "mes"], name="reporte_unico_por_cliente_y_mes")]

    def __str__(self):
        return f"{self.cliente} · {self.mes:%m-%Y}"
