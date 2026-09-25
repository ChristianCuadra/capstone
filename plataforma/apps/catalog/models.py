"""Catálogo de planes y servicios (Documento de Alcance 5.2).

Todo se administra como datos: crear un plan nuevo (p. ej. un plan económico para pymes)
es una operación de administración, no un cambio de código. Los planes se cobran mensualmente.
"""

from django.core.exceptions import ValidationError
from django.db import models


class TipoEntregable(models.Model):
    """Vocabulario del negocio: historia, carrusel, reel, calendario, copywriting..."""

    nombre = models.CharField(max_length=80, unique=True)
    nombre_plural = models.CharField("nombre en plural", max_length=80, blank=True, help_text="Ej.: historias. Se usa en «16 historias».")
    slug = models.SlugField(unique=True)
    tiene_cuota = models.BooleanField(
        "tiene cuota mensual",
        default=False,
        help_text="Marcado: se entrega una cantidad al mes y cuenta para el cumplimiento del plan (historias, carruseles, reels).",
    )
    orden = models.PositiveSmallIntegerField(default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "tipos_entregable"
        verbose_name = "tipo de entregable"
        verbose_name_plural = "tipos de entregable"
        ordering = ["orden", "nombre"]

    def __str__(self):
        return self.nombre


class Servicio(models.Model):
    """Servicio contratable por separado. No participa del ciclo mensual del plan, salvo los de modalidad mensual."""

    class ModalidadCobro(models.TextChoices):
        POR_HORA = "hora", "Por hora"
        PAGO_UNICO = "unico", "Pago único"
        POR_CAMPANA = "campana", "Por campaña"
        POR_PAQUETE = "paquete", "Por paquete"
        MENSUAL = "mensual", "Mensual"

    nombre = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(unique=True)
    descripcion = models.TextField("descripción", blank=True)
    precio = models.PositiveIntegerField("precio (CLP)")
    modalidad_cobro = models.CharField("modalidad de cobro", max_length=10, choices=ModalidadCobro.choices)
    visible_en_sitio = models.BooleanField("visible en el sitio", default=True)
    orden = models.PositiveSmallIntegerField(default=0)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "servicios"
        verbose_name = "servicio"
        verbose_name_plural = "servicios"
        ordering = ["orden", "nombre"]

    def __str__(self):
        return self.nombre


class Plan(models.Model):
    """Plantilla mensual que combina tipos de entregable con cantidades y un precio."""

    nombre = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(unique=True)
    descripcion = models.TextField("descripción", blank=True)
    precio_mensual = models.PositiveIntegerField("precio mensual (CLP)")
    precio_primer_mes = models.PositiveIntegerField(
        "precio del primer mes (CLP)",
        null=True,
        blank=True,
        help_text="Solo si el primer mes cuesta distinto (p. ej. Expansión). Vacío = igual al mensual.",
    )
    destacado = models.BooleanField("destacado en el sitio", default=False)
    etiqueta = models.CharField(max_length=40, blank=True, help_text="Ej.: MÁS CONTRATADO. Se muestra sobre la tarjeta.")
    visible_en_sitio = models.BooleanField("visible en el sitio", default=True)
    orden = models.PositiveSmallIntegerField(default=0)
    activo = models.BooleanField(default=True, help_text="Desmarcar en vez de borrar: los contratos existentes lo siguen usando.")
    tipos_entregable = models.ManyToManyField(TipoEntregable, through="PlanEntregable", related_name="planes")
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "planes"
        verbose_name = "plan"
        verbose_name_plural = "planes"
        ordering = ["orden", "precio_mensual"]

    def __str__(self):
        return self.nombre


class PlanEntregable(models.Model):
    """Qué incluye un plan. Con cuota: cantidad mensual; sin cuota: incluido sin cantidad."""

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="entregables")
    tipo_entregable = models.ForeignKey(TipoEntregable, on_delete=models.PROTECT, verbose_name="entregable")
    cantidad_mensual = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = "planes_entregables"
        verbose_name = "entregable del plan"
        verbose_name_plural = "entregables del plan"
        ordering = ["tipo_entregable__orden"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "tipo_entregable"], name="plan_entregable_unico"),
        ]

    def __str__(self):
        return self.texto

    def clean(self):
        if self.tipo_entregable_id is None:
            return
        if self.tipo_entregable.tiene_cuota and not self.cantidad_mensual:
            raise ValidationError({"cantidad_mensual": "Este entregable tiene cuota mensual: indica la cantidad."})
        if not self.tipo_entregable.tiene_cuota and self.cantidad_mensual:
            raise ValidationError({"cantidad_mensual": "Este entregable no tiene cuota mensual: deja la cantidad vacía."})

    @property
    def texto(self):
        """«16 historias» o «Branding»."""
        tipo = self.tipo_entregable
        if self.cantidad_mensual:
            return f"{self.cantidad_mensual} {(tipo.nombre_plural or tipo.nombre).lower()}"
        return tipo.nombre
