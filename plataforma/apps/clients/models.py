from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property

from apps.core.models import TenantModel
from apps.crm.models import REGIONES, RUBROS


class Cliente(models.Model):
    """Cliente de la agencia (tenant). Ficha comercial y contrato vigente (PC-CLI-01, Alcance 5.4)."""

    class FormaPago(models.TextChoices):
        TRANSFERENCIA = "transferencia", "Transferencia"
        TARJETA = "tarjeta", "Tarjeta"
        OTRA = "otra", "Otra"

    nombre = models.CharField(max_length=200)
    activo = models.BooleanField(default=True)

    # Datos comerciales
    rut = models.CharField("RUT", max_length=12, blank=True, help_text="Formato 12.345.678-5. Vacío si aún no lo tiene (p. ej. empresa extranjera).")
    rubro = models.CharField(max_length=60, choices=[(r, r) for r in RUBROS], blank=True)
    region = models.CharField("región", max_length=60, choices=[(r, r) for r in REGIONES], blank=True)

    # Contacto principal
    contacto_nombre = models.CharField("contacto principal", max_length=120, blank=True)
    contacto_correo = models.EmailField("correo del contacto", blank=True)
    contacto_telefono = models.CharField("teléfono del contacto", max_length=30, blank=True)

    # Contrato vigente
    plan = models.ForeignKey(
        "catalog.Plan", null=True, blank=True, on_delete=models.SET_NULL, related_name="clientes", verbose_name="plan contratado"
    )
    fecha_inicio_contrato = models.DateField("inicio del contrato", null=True, blank=True)
    forma_pago = models.CharField("forma de pago", max_length=15, choices=FormaPago.choices, blank=True)

    # Marca y objetivos (alimentan la generación asistida de contenido)
    directrices_marca = models.TextField("directrices de marca", blank=True, help_text="Tono, público objetivo, lineamientos y restricciones.")
    objetivos = models.TextField(blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "clientes"
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


def ruta_documento(instance, filename):
    return f"clientes/{instance.cliente_id}/documentos/{filename}"


class DocumentoCliente(TenantModel):
    """Documento adjunto a la ficha del cliente (contrato, directrices, propuestas). PC-CLI-02."""

    class Tipo(models.TextChoices):
        CONTRATO = "contrato", "Contrato"
        DIRECTRICES = "directrices", "Directrices de marca"
        PROPUESTA = "propuesta", "Propuesta o cotización"
        OTRO = "otro", "Otro"

    nombre = models.CharField(max_length=150)
    tipo = models.CharField(max_length=15, choices=Tipo.choices, default=Tipo.OTRO)
    archivo = models.FileField(upload_to=ruta_documento)
    subido_por = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="subido por"
    )

    class Meta:
        db_table = "clientes_documentos"
        verbose_name = "documento del cliente"
        verbose_name_plural = "documentos del cliente"
        ordering = ["-creado_en"]

    def __str__(self):
        return self.nombre


class KPICliente(TenantModel):
    """KPI comprometido con un cliente: valor inicial y meta. El avance sale de las mediciones (Alcance 5.4 y 5.8).

    Lista inicial solo con indicadores donde "más es mejor"; los de publicidad (CPC, costo por resultado)
    quedan para cuando existan campañas, porque su cumplimiento se calcula al revés.
    """

    class Indicador(models.TextChoices):
        SEGUIDORES = "seguidores", "Seguidores"
        ALCANCE = "alcance", "Alcance"
        INTERACCIONES = "interacciones", "Interacciones"
        VISITAS = "visitas", "Visitas"
        CLICS = "clics", "Clics"

    DIAS_PARA_DESACTUALIZADO = 30

    indicador = models.CharField(max_length=20, choices=Indicador.choices)
    valor_inicial = models.DecimalField("valor inicial", max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    meta = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])

    class Meta:
        db_table = "clientes_kpis"
        verbose_name = "KPI del cliente"
        verbose_name_plural = "KPIs del cliente"
        ordering = ["indicador"]
        constraints = [
            models.UniqueConstraint(fields=["cliente", "indicador"], name="kpi_unico_por_cliente_e_indicador"),
            models.CheckConstraint(check=models.Q(meta__gt=models.F("valor_inicial")), name="kpi_meta_mayor_que_inicial"),
        ]

    def __str__(self):
        return f"{self.get_indicador_display()} · {self.cliente}"

    def clean(self):
        if self.meta is not None and self.valor_inicial is not None and self.meta <= self.valor_inicial:
            raise ValidationError({"meta": "La meta debe ser mayor que el valor inicial."})

    @cached_property
    def ultima_medicion(self):
        return self.mediciones.order_by("-fecha", "-pk").first()

    @property
    def valor_actual(self):
        medicion = self.ultima_medicion
        return medicion.valor if medicion else None

    @property
    def porcentaje_cumplimiento(self):
        """Avance respecto de la meta, en %. Vacío sin mediciones; nunca negativo; puede superar 100."""
        actual = self.valor_actual
        if actual is None or self.meta <= self.valor_inicial:
            return None
        avance = (actual - self.valor_inicial) / (self.meta - self.valor_inicial) * 100
        return max(Decimal("0"), avance.quantize(Decimal("0.1")))

    @property
    def desactualizado(self):
        medicion = self.ultima_medicion
        if medicion is None:
            return True
        return (timezone.localdate() - medicion.fecha).days > self.DIAS_PARA_DESACTUALIZADO


class MedicionKPI(TenantModel):
    """Una medición fechada de un KPI. El historial se conserva: el valor actual es la última."""

    class Fuente(models.TextChoices):
        MANUAL = "manual", "Manual"
        IMPORTADA = "importada", "Importada"

    kpi = models.ForeignKey(KPICliente, on_delete=models.CASCADE, related_name="mediciones")
    fecha = models.DateField()
    valor = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    fuente = models.CharField(max_length=10, choices=Fuente.choices, default=Fuente.MANUAL)
    registrado_por = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="registrado por"
    )

    class Meta:
        db_table = "clientes_kpis_mediciones"
        verbose_name = "medición de KPI"
        verbose_name_plural = "mediciones de KPI"
        ordering = ["-fecha", "-pk"]

    def __str__(self):
        return f"{self.kpi} · {self.fecha} · {self.valor}"
