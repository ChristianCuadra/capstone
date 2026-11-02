"""Datos de red de la petición."""


def ip_del_cliente(request):
    """IP pública de quien hace la petición. En Vercel la entrega su proxy en X-Forwarded-For (primer valor)."""
    if request is None:
        return ""
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return reenviada.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")
