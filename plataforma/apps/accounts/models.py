from django.contrib.auth.models import AbstractUser
from django.db import models


class Rol(models.TextChoices):
    """Roles del sistema (Documento de Alcance 4.3 / Especificación de Requerimientos, sección 2)."""

    ADMINISTRADORA = "administradora", "Administradora"
    COLABORADORA = "colaboradora", "Colaboradora"
    CLIENTE_APROBADOR = "cliente_aprobador", "Cliente aprobador"
    CLIENTE_LECTOR = "cliente_lector", "Cliente lector"


class User(AbstractUser):
    """Usuario propio desde el inicio: cambiar AUTH_USER_MODEL después del primer migrate es muy costoso.

    Las columnas (username, email, first_name...) las define Django y se mantienen;
    solo la tabla se nombra en español.
    """

    rol = models.CharField(
        max_length=20,
        choices=Rol.choices,
        blank=True,
        verbose_name="rol",
        help_text="Rol dentro de la plataforma (Alcance 4.3). Vacío = sin rol asignado todavía.",
    )
    cliente = models.ForeignKey(
        "clients.Cliente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuarios",
        verbose_name="cliente",
        help_text="Empresa a la que pertenece. Solo aplica a Cliente aprobador / Cliente lector.",
    )
    clientes_asignados = models.ManyToManyField(
        "clients.Cliente",
        blank=True,
        related_name="colaboradoras",
        verbose_name="clientes asignados",
        help_text="Clientes que puede ver. Solo aplica al rol Colaboradora.",
    )

    class Meta(AbstractUser.Meta):
        db_table = "usuarios"
        swappable = "AUTH_USER_MODEL"
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def save(self, *args, **kwargs):
        # El email se normaliza a minúsculas antes de guardar: django-allauth busca
        # el usuario por email pasándolo a minúsculas, y una comparación exacta contra
        # un email guardado con mayúsculas puede no calzar (SQLite/Postgres son
        # sensibles a mayúsculas en "="), lo que impediría iniciar sesión.
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)

    @property
    def es_cliente(self):
        """True si el rol es Cliente aprobador o Cliente lector (Alcance 4.3)."""
        return self.rol in (Rol.CLIENTE_APROBADOR, Rol.CLIENTE_LECTOR)

    @property
    def es_cliente_aprobador(self):
        return self.rol == Rol.CLIENTE_APROBADOR

    @property
    def es_equipo_agencia(self):
        """True si el rol es Administradora o Colaboradora."""
        return self.rol in (Rol.ADMINISTRADORA, Rol.COLABORADORA)
