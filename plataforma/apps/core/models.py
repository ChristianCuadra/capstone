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


class RegistroAuditoria(models.Model):
    """Bitácora de acciones administrativas sensibles (Documento de Alcance 9.2, RNF-01).

    Por ahora se registra manualmente desde las vistas que lo requieren
    (alta/edición de usuarios); se puede ampliar a otras acciones sensibles después.
    """

    class Accion(models.TextChoices):
        CREAR = "crear", "Crear"
        EDITAR = "editar", "Editar"
        ELIMINAR = "eliminar", "Eliminar"

    usuario = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="registros_auditoria",
        verbose_name="usuario",
        help_text="Quién ejecutó la acción. Vacío si la cuenta fue eliminada después.",
    )
    accion = models.CharField(max_length=10, choices=Accion.choices, verbose_name="acción")
    entidad = models.CharField(max_length=100, verbose_name="entidad", help_text="Qué se modificó, ej. 'usuario'")
    entidad_id = models.CharField(max_length=50, blank=True, verbose_name="ID de la entidad")
    detalle = models.CharField(max_length=255, blank=True, verbose_name="detalle")
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name="fecha")

    class Meta:
        db_table = "registro_auditoria"
        verbose_name = "registro de auditoría"
        verbose_name_plural = "registros de auditoría"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.creado_en:%d-%m-%Y %H:%M} · {self.usuario} · {self.get_accion_display()} {self.entidad} {self.entidad_id}"

    @classmethod
    def registrar(cls, *, usuario, accion, entidad, entidad_id="", detalle=""):
        """Atajo para dejar una entrada en la bitácora desde cualquier vista."""
        return cls.objects.create(
            usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
            accion=accion,
            entidad=entidad,
            entidad_id=str(entidad_id),
            detalle=detalle,
        )
