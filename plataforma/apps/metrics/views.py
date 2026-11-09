"""Métricas: carga por archivo (PC-MET-01), dashboard de la agencia (PC-DSH-01) y del cliente (PC-DSH-02)."""

from datetime import date, timedelta

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import requiere_equipo, requiere_rol_cliente
from apps.clients.models import KPICliente
from apps.core.access import clientes_visibles, obtener_cliente_visible, puede_aprobar
from apps.core.models import RegistroAuditoria
from apps.reports.models import ReporteMensual

from .importador import TAMANO_MAX_MB, ErrorArchivo, importar, plantilla_csv
from .models import Fuente, ImportacionMetricas, MetricaDiaria
from .resumen import resumen_metricas

ATAJOS = [("mes", "Este mes"), ("mes_anterior", "Mes anterior"), ("3_meses", "Últimos 3 meses"), ("anio", "Este año")]


def _fecha_param(valor):
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        return None


def rango_desde_request(request, hoy=None):
    """(desde, hasta, atajo) a partir de ?periodo= o de ?desde=&hasta= (criterio 2 de PC-DSH-01)."""
    hoy = hoy or timezone.localdate()
    inicio_mes = hoy.replace(day=1)
    periodo = request.GET.get("periodo")
    desde, hasta = _fecha_param(request.GET.get("desde")), _fecha_param(request.GET.get("hasta"))
    if desde and hasta and not periodo:
        if desde > hasta:
            desde, hasta = hasta, desde
        return desde, hasta, ""
    if periodo == "mes":
        return inicio_mes, hoy, periodo
    if periodo == "mes_anterior":
        fin = inicio_mes - timedelta(days=1)
        return fin.replace(day=1), fin, periodo
    if periodo == "anio":
        return date(hoy.year, 1, 1), hoy, periodo
    inicio = inicio_mes
    for _ in range(2):
        inicio = (inicio - timedelta(days=1)).replace(day=1)
    return inicio, hoy, "3_meses"


def _cliente_del_panel(request):
    """Cliente pedido por ?cliente=, o el cliente activo del panel, o el primero visible."""
    elegido = request.GET.get("cliente") or request.POST.get("cliente") or getattr(request, "client_id", None)
    if elegido:
        return obtener_cliente_visible(request.user, elegido)
    return clientes_visibles(request.user).filter(activo=True).order_by("nombre").first()


def _meses_para_reporte(hoy):
    """Mes anterior y los 5 previos, más el actual (para generar el reporte de un mes cerrado o en curso)."""
    meses, primero = [], hoy.replace(day=1)
    for _ in range(7):
        meses.append(primero)
        primero = (primero - timedelta(days=1)).replace(day=1)
    return meses


@requiere_equipo
def panel_metricas(request):
    from apps.crm.views import contexto_panel
    from apps.reports.servicios import mes_texto

    cliente = _cliente_del_panel(request)
    desde, hasta, atajo = rango_desde_request(request)
    contexto = {
        "cliente": cliente,
        "clientes": clientes_visibles(request.user).filter(activo=True).order_by("nombre"),
        "desde": desde, "hasta": hasta, "atajo": atajo, "atajos": ATAJOS,
        "fuentes": Fuente.choices, "tamano_max": TAMANO_MAX_MB,
        "puede_administrar": puede_aprobar(request.user),
    }
    if cliente:
        hoy = timezone.localdate()
        contexto.update({
            "resumen": resumen_metricas(cliente, desde, hasta),
            "kpis": KPICliente.all_objects.filter(cliente=cliente),
            "importaciones": ImportacionMetricas.all_objects.filter(cliente=cliente).select_related("subido_por")[:5],
            "reportes": ReporteMensual.all_objects.filter(cliente=cliente),
            "meses_reporte": [(m.isoformat()[:7], mes_texto(m)) for m in _meses_para_reporte(hoy)],
        })
    return render(request, "metrics/panel_metricas.html", contexto_panel(request, "metricas", **contexto))


@requiere_equipo
@require_POST
def importar_archivo(request):
    cliente = _cliente_del_panel(request)
    destino = reverse("metrics:panel") + (f"?cliente={cliente.pk}" if cliente else "")
    if not puede_aprobar(request.user):
        messages.error(request, "Solo la administradora puede cargar métricas.")
        return redirect(destino)
    archivo = request.FILES.get("archivo")
    fuente = request.POST.get("fuente")
    if not cliente or not archivo or fuente not in Fuente.values:
        messages.error(request, "Elige el cliente, la fuente y el archivo.")
        return redirect(destino)
    try:
        importacion = importar(archivo, cliente, fuente, request.user)
    except ErrorArchivo as e:
        messages.error(request, "No se cargó ningún dato porque el archivo tiene errores:")
        for error in e.errores:
            messages.error(request, error)
        return redirect(destino)
    RegistroAuditoria.registrar(
        usuario=request.user, accion=RegistroAuditoria.Accion.CREAR, entidad="métricas",
        entidad_id=importacion.pk, detalle=f"{importacion.nombre_archivo} · {cliente.nombre} · {importacion.filas} días"[:255],
    )
    messages.success(
        request,
        f"Se cargaron {importacion.filas} días de {importacion.get_fuente_display()} "
        f"({importacion.desde:%d-%m-%Y} al {importacion.hasta:%d-%m-%Y}). Los días que ya existían se actualizaron.",
    )
    return redirect(f"{destino}&desde={importacion.desde}&hasta={importacion.hasta}")


@requiere_equipo
def descargar_plantilla(request):
    respuesta = HttpResponse(plantilla_csv(), content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = 'attachment; filename="plantilla-metricas-cosmopolitan.csv"'
    return respuesta


@requiere_rol_cliente
def portal_metricas(request):
    """Métricas y reportes del cliente, solo de su empresa (PC-DSH-02 y PC-REP-01)."""
    from apps.content.views import contexto_portal

    cliente = request.user.cliente
    desde, hasta, atajo = rango_desde_request(request)
    contexto = {"desde": desde, "hasta": hasta, "atajo": atajo, "atajos": ATAJOS, "resumen": {"hay_datos": False}, "reportes": []}
    if cliente:
        contexto["resumen"] = resumen_metricas(cliente, desde, hasta)
        contexto["kpis"] = KPICliente.all_objects.filter(cliente=cliente)
        contexto["reportes"] = ReporteMensual.all_objects.filter(cliente=cliente, estado=ReporteMensual.Estado.APROBADO)
        contexto["hay_datos_alguna_vez"] = MetricaDiaria.all_objects.filter(cliente=cliente).exists()
    contexto["hay_datos"] = contexto["resumen"].get("hay_datos")
    return render(request, "content/metricas.html", contexto_portal(request, "metricas", **contexto))
