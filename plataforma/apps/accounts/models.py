from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Usuario propio desde el inicio: cambiar AUTH_USER_MODEL después del primer migrate es muy costoso.

    Las columnas (username, email, first_name...) las define Django y se mantienen;
    solo la tabla se nombra en español.
    """

    class Meta(AbstractUser.Meta):
        db_table = "usuarios"
        swappable = "AUTH_USER_MODEL"
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
