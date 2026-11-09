from .models import Notificacion


def notificaciones(request):
    """Cantidad de avisos sin leer para la campana del panel y del portal."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    return {"notificaciones_sin_leer": Notificacion.objects.filter(usuario=user, leida=False).count()}
