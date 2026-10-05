from django.db import models

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
