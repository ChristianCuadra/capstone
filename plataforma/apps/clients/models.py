from django.db import models


class Cliente(models.Model):
    """Cliente de la agencia (tenant). Placeholder: se completará más adelante."""

    nombre = models.CharField(max_length=200)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "clientes"
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre
