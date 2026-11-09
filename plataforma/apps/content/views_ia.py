"""Borrador de copy con IA desde el calendario del panel (PC-IA-03)."""

from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.accounts.decorators import requiere_equipo
from apps.ai.services import ErrorIA, IANoConfigurada, generar_copy
from apps.catalog.models import TipoEntregable

from .models import RedSocial


@requiere_equipo
@require_POST
def copy_ia(request):
    from .views import _clientes_del_panel, _entero

    cliente = _clientes_del_panel(request.user).filter(pk=_entero(request.POST.get("cliente_id"))).first()
    if not cliente:
        return JsonResponse({"error": "Elige un cliente."}, status=400)
    titulo = (request.POST.get("titulo") or "").strip()[:200]
    if not titulo:
        return JsonResponse({"error": "Escribe primero el título o concepto."}, status=400)
    red = dict(RedSocial.choices).get(request.POST.get("red_social"), "Instagram")
    tipo = TipoEntregable.objects.filter(pk=_entero(request.POST.get("tipo_entregable"))).values_list("nombre", flat=True).first() or ""
    try:
        texto = generar_copy(cliente, titulo, red, tipo, request.user)
    except IANoConfigurada:
        return JsonResponse({"error": "La IA no está configurada (falta la clave en el archivo .env). Escribe el copy a mano."}, status=503)
    except ErrorIA as e:
        return JsonResponse({"error": str(e)}, status=502)
    from apps.ai.models import RegistroIA

    ultimo = RegistroIA.objects.filter(usuario=request.user, exitoso=True).order_by("-creado_en").first()
    return JsonResponse({"texto": texto, "proveedor": ultimo.proveedor if ultimo else "IA"})
