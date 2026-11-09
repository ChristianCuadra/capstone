from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import Notificacion


def _contexto_layout(request, **context):
    """Las notificaciones se muestran dentro del layout que le corresponde a cada usuario."""
    if request.user.es_cliente:
        from apps.content.views import contexto_portal

        context = contexto_portal(request, "notificaciones", **context)
        context["layout"] = "content/base_portal.html"
    else:
        from apps.crm.views import contexto_panel

        context = contexto_panel(request, "notificaciones", **context)
        context["layout"] = "crm/base_panel.html"
    return context


@login_required
def lista(request):
    avisos = Notificacion.objects.filter(usuario=request.user)[:100]
    return render(request, "notifications/lista.html", _contexto_layout(request, avisos=avisos))


@login_required
def abrir(request, pk):
    """Marca el aviso como leído y lleva a su enlace."""
    aviso = get_object_or_404(Notificacion, pk=pk, usuario=request.user)
    if not aviso.leida:
        aviso.leida = True
        aviso.save(update_fields=["leida"])
    if aviso.url and url_has_allowed_host_and_scheme(aviso.url, allowed_hosts={request.get_host()}):
        return redirect(aviso.url)
    return redirect("notifications:lista")


@login_required
@require_POST
def marcar_todas(request):
    Notificacion.objects.filter(usuario=request.user, leida=False).update(leida=True)
    return redirect("notifications:lista")
