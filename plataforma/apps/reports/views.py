"""Reporte mensual: borrador con IA (PC-IA-02), revisión y aprobación humana (PC-IA-04), descarga en PDF (PC-REP-01)."""

from datetime import date

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import requiere_equipo, requiere_rol_cliente
from apps.ai.services import ErrorIA, IANoConfigurada, generar_reporte_mensual
from apps.core.access import clientes_visibles, obtener_cliente_visible, puede_aprobar
from apps.core.models import RegistroAuditoria
from apps.notifications.services import notificar, usuarios_del_cliente

from .models import ReporteMensual
from .pdf import generar_pdf
from .servicios import borrador_sin_ia, datos_del_mes, mes_texto


def _reporte_del_equipo(user, pk):
    try:
        return ReporteMensual.all_objects.select_related("cliente").get(pk=int(pk), cliente__in=clientes_visibles(user))
    except (ReporteMensual.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404 from exc


@requiere_equipo
@require_POST
def generar(request):
    """Crea (o regenera, si sigue en borrador) el reporte de un mes. Con IA si está disponible."""
    cliente = obtener_cliente_visible(request.user, request.POST.get("cliente"))
    try:
        anio, mes = (int(x) for x in request.POST.get("mes", "").split("-"))
        primero = date(anio, mes, 1)
    except ValueError:
        messages.error(request, "Elige el mes del reporte.")
        return redirect(reverse("metrics:panel") + f"?cliente={cliente.pk}")
    reporte, _ = ReporteMensual.all_objects.get_or_create(cliente=cliente, mes=primero, defaults={"creado_por": request.user})
    if reporte.estado == ReporteMensual.Estado.APROBADO:
        messages.error(request, "Ese reporte ya está aprobado. Vuelve a dejarlo en borrador para regenerarlo.")
        return redirect("reports:editar", pk=reporte.pk)

    resumen, cumplimiento = datos_del_mes(cliente, primero)
    usar_ia = request.POST.get("con_ia") == "1"
    if usar_ia:
        try:
            reporte.contenido = generar_reporte_mensual(cliente, mes_texto(primero), resumen, cumplimiento, request.user)
            reporte.generado_con_ia = True
            messages.success(request, "Borrador generado con IA solo con los datos de este cliente. Revísalo y edítalo antes de aprobarlo.")
        except IANoConfigurada:
            usar_ia = False
            messages.error(request, "La IA no está configurada. Se creó una plantilla con los datos del mes para escribirlo a mano.")
        except ErrorIA as e:
            usar_ia = False
            messages.error(request, f"No se pudo usar la IA. {e} Se creó una plantilla con los datos del mes.")
    if not usar_ia:
        reporte.contenido = borrador_sin_ia(cliente, primero, resumen, cumplimiento)
        reporte.generado_con_ia = False
    reporte.save()
    return redirect("reports:editar", pk=reporte.pk)


@requiere_equipo
def editar(request, pk):
    from apps.crm.views import contexto_panel

    reporte = _reporte_del_equipo(request.user, pk)
    puede_aprobar_reporte = puede_aprobar(request.user)
    if request.method == "POST":
        accion = request.POST.get("accion", "guardar")
        if accion == "volver_borrador":
            if not puede_aprobar_reporte:
                messages.error(request, "Solo la administradora puede cambiar el estado del reporte.")
            else:
                reporte.estado = ReporteMensual.Estado.BORRADOR
                reporte.aprobado_por = None
                reporte.fecha_aprobacion = None
                reporte.save()
                messages.success(request, "El reporte volvió a borrador y dejó de estar visible para el cliente.")
            return redirect("reports:editar", pk=reporte.pk)
        if reporte.estado == ReporteMensual.Estado.APROBADO:
            messages.error(request, "El reporte está aprobado. Vuelve a dejarlo en borrador para editarlo.")
            return redirect("reports:editar", pk=reporte.pk)
        contenido = (request.POST.get("contenido") or "").strip()
        if not contenido:
            messages.error(request, "El reporte no puede quedar vacío.")
            return redirect("reports:editar", pk=reporte.pk)
        reporte.contenido = contenido
        if accion == "aprobar":
            if not puede_aprobar_reporte:
                messages.error(request, "Solo la administradora puede aprobar el reporte.")
                reporte.save()
                return redirect("reports:editar", pk=reporte.pk)
            reporte.estado = ReporteMensual.Estado.APROBADO
            reporte.aprobado_por = request.user
            reporte.fecha_aprobacion = timezone.now()
            reporte.save()
            RegistroAuditoria.registrar(
                usuario=request.user, accion=RegistroAuditoria.Accion.EDITAR, entidad="reporte mensual",
                entidad_id=reporte.pk, detalle=f"Aprobado · {reporte.cliente.nombre} · {mes_texto(reporte.mes)}"[:255],
            )
            notificar(
                usuarios_del_cliente(reporte.cliente),
                f"Tu reporte de {mes_texto(reporte.mes)} está disponible",
                "Puedes verlo y descargarlo en PDF desde la sección Métricas del portal.",
                url=reverse("content:metricas"),
                request=request,
            )
            messages.success(request, "Reporte aprobado. El cliente ya puede descargarlo y recibió un aviso.")
        else:
            reporte.save()
            messages.success(request, "Cambios guardados.")
        return redirect("reports:editar", pk=reporte.pk)

    resumen, cumplimiento = datos_del_mes(reporte.cliente, reporte.mes)
    return render(request, "reports/editar.html", contexto_panel(
        request, "metricas",
        reporte=reporte, mes_nombre=mes_texto(reporte.mes), resumen=resumen, cumplimiento=cumplimiento,
        puede_aprobar=puede_aprobar_reporte,
    ))


def _respuesta_pdf(request, reporte):
    from apps.website.models import ConfiguracionAgencia

    resumen, cumplimiento = datos_del_mes(reporte.cliente, reporte.mes)
    agencia = getattr(ConfiguracionAgencia.objects.first(), "nombre", "") or "Agencia Cosmopolitan"
    contenido = generar_pdf(reporte, agencia, mes_texto(reporte.mes), resumen, cumplimiento)
    nombre = f"reporte-{reporte.mes:%Y-%m}-{reporte.cliente.nombre}".replace(" ", "-").lower()
    respuesta = HttpResponse(contenido, content_type="application/pdf")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}.pdf"'
    return respuesta


@requiere_equipo
def pdf_panel(request, pk):
    return _respuesta_pdf(request, _reporte_del_equipo(request.user, pk))


@requiere_rol_cliente
def pdf_portal(request, pk):
    """Solo reportes aprobados y de la empresa del cliente (criterios 2 y 3 de PC-REP-01)."""
    cliente = request.user.cliente
    try:
        reporte = ReporteMensual.all_objects.select_related("cliente").get(
            pk=int(pk), cliente=cliente, estado=ReporteMensual.Estado.APROBADO
        )
    except (ReporteMensual.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404 from exc
    RegistroAuditoria.registrar(
        usuario=request.user, accion=RegistroAuditoria.Accion.DESCARGAR, entidad="reporte mensual",
        entidad_id=reporte.pk, detalle=f"{cliente.nombre} · {mes_texto(reporte.mes)}"[:255],
    )
    return _respuesta_pdf(request, reporte)
