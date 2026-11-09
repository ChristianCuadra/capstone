"""Métricas de redes y campañas por cliente (PC-MET-01), base de los dashboards (PC-DSH-01 y PC-DSH-02)."""

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class Fuente(models.TextChoices):
    INSTAGRAM = "instagram", "Instagram (orgánico)"
    META_ADS = "meta_ads", "Meta Ads (campañas)"


class ImportacionMetricas(TenantModel):
    """Cada archivo cargado: quién, cuándo, qué rango cubre y cuántas filas trajo."""

    fuente = models.CharField(max_length=12, choices=Fuente.choices)
    nombre_archivo = models.CharField(max_length=200)
    filas = models.PositiveIntegerField(default=0)
    desde = models.DateField(null=True)
    hasta = models.DateField(null=True)
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        db_table = "metricas_importaciones"
        verbose_name = "importación de métricas"
        verbose_name_plural = "importaciones de métricas"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.cliente} · {self.get_fuente_display()} · {self.nombre_archivo}"


class MetricaDiaria(TenantModel):
    """Un día de una fuente para un cliente. Cargar de nuevo el mismo día lo reemplaza (no se duplica)."""

    fecha = models.DateField()
    fuente = models.CharField(max_length=12, choices=Fuente.choices)
    alcance = models.PositiveIntegerField(null=True, blank=True)
    impresiones = models.PositiveIntegerField(null=True, blank=True)
    interacciones = models.PositiveIntegerField(null=True, blank=True)
    seguidores = models.PositiveIntegerField("seguidores totales", null=True, blank=True)
    clics = models.PositiveIntegerField(null=True, blank=True)
    gasto = models.DecimalField("importe gastado (CLP)", max_digits=12, decimal_places=2, null=True, blank=True)
    resultados = models.PositiveIntegerField("resultados / conversiones", null=True, blank=True)
    importacion = models.ForeignKey(ImportacionMetricas, null=True, on_delete=models.SET_NULL, related_name="metricas")

    class Meta:
        db_table = "metricas_diarias"
        verbose_name = "métrica diaria"
        verbose_name_plural = "métricas diarias"
        ordering = ["fecha"]
        constraints = [
            models.UniqueConstraint(fields=["cliente", "fecha", "fuente"], name="metrica_unica_por_dia_y_fuente"),
        ]

    def __str__(self):
        return f"{self.cliente} · {self.fecha} · {self.fuente}"
