from django.db import models

from .context import get_current_client_id


class TenantQuerySet(models.QuerySet):
    def para_cliente(self, cliente):
        return self.filter(cliente=cliente)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Filtra automáticamente por el cliente activo en el contexto de la petición.

    Si no hay cliente en el contexto (shell, tareas Celery, comandos de gestión),
    no filtra. Para consultas explícitamente globales usar `Model.all_objects`.
    """

    def get_queryset(self):
        queryset = super().get_queryset()
        cliente_id = get_current_client_id()
        if cliente_id is not None:
            queryset = queryset.filter(cliente_id=cliente_id)
        return queryset


class TenantModel(models.Model):
    """Base de toda entidad que pertenece a un cliente (aislamiento entre clientes)."""

    cliente = models.ForeignKey(
        "clients.Cliente",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.cliente_id is None:
            self.cliente_id = get_current_client_id()
        super().save(*args, **kwargs)
