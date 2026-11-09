"""Solicitudes y archivos entre el cliente y la agencia (PC-SOL-01) con sus avisos (PC-SOL-02).

Portal: el cliente (aprobador o lector) crea solicitudes con archivos adjuntos y sigue el hilo.
Panel: el equipo ve las solicitudes de los clientes que puede ver, responde (con archivos) y las cierra.
"""

import os

from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.decorators import requiere_equipo, requiere_rol_cliente
from apps.core.access import clientes_visibles
from apps.core.models import RegistroAuditoria
from apps.notifications.services import equipo_del_cliente, notificar, usuarios_del_cliente

from .models import (
    EXTENSIONES_SOLICITUD,
    MAX_ARCHIVOS_POR_MENSAJE,
    TAMANO_MAX_SOLICITUD_MB,
    ArchivoSolicitud,
    MensajeSolicitud,
    Solicitud,
)

LARGO_MAX_ASUNTO = 150
LARGO_MAX_TEXTO = 5000


def validar_archivos(archivos):
    """Lista de errores (vacía si todos los archivos son válidos). Se valida antes de guardar nada."""
    errores = []
    if len(archivos) > MAX_ARCHIVOS_POR_MENSAJE:
        errores.append(f"Puedes adjuntar hasta {MAX_ARCHIVOS_POR_MENSAJE} archivos por mensaje.")
    for archivo in archivos:
        extension = os.path.splitext(archivo.name)[1].lower()
        if extension not in EXTENSIONES_SOLICITUD:
            errores.append(f"«{archivo.name}»: formato no permitido. Usa PDF, Word, Excel, PowerPoint, imagen, video, texto o ZIP.")
        elif archivo.size > TAMANO_MAX_SOLICITUD_MB * 1024 * 1024:
            errores.append(f"«{archivo.name}» supera los {TAMANO_MAX_SOLICITUD_MB} MB.")
    return errores


def _guardar_mensaje(solicitud, usuario, texto, archivos):
    mensaje = MensajeSolicitud.objects.create(solicitud=solicitud, usuario=usuario, texto=texto)
    for archivo in archivos:
        ArchivoSolicitud.objects.create(mensaje=mensaje, archivo=archivo, nombre=archivo.name[:200], tamano=archivo.size)
    return mensaje


def _leer_formulario(request, con_asunto):
    """(asunto, texto, archivos, errores) del POST."""
    asunto = (request.POST.get("asunto") or "").strip()
    texto = (request.POST.get("texto") or "").strip()
    archivos = request.FILES.getlist("archivos")
    errores = []
    if con_asunto and not asunto:
        errores.append("Escribe el asunto de la solicitud.")
    if len(asunto) > LARGO_MAX_ASUNTO:
        errores.append(f"El asunto puede tener hasta {LARGO_MAX_ASUNTO} caracteres.")
    if not texto:
        errores.append("Escribe el mensaje.")
    if len(texto) > LARGO_MAX_TEXTO:
        errores.append(f"El mensaje puede tener hasta {LARGO_MAX_TEXTO} caracteres.")
    errores += validar_archivos(archivos)
    return asunto, texto, archivos, errores


def _hilo(solicitud):
    return solicitud.mensajes.select_related("usuario").prefetch_related("archivos")


def _descargar(archivo):
    try:
        abierto = archivo.archivo.open("rb")
    except (FileNotFoundError, ValueError) as exc:
        raise Http404("El archivo ya no está disponible.") from exc
    return FileResponse(abierto, as_attachment=True, filename=archivo.nombre)


# ── Portal del cliente ──────────────────────────────────────────────────────

def _solicitudes_del_cliente(request):
    cliente = request.user.cliente
    if not cliente:
        return Solicitud.all_objects.none()
    return Solicitud.all_objects.filter(cliente=cliente)


@requiere_rol_cliente
def portal_solicitudes(request):
    from .views import contexto_portal

    cliente = request.user.cliente
    if request.method == "POST":
        if not cliente:
            messages.error(request, "Tu cuenta no está asociada a una empresa. Escríbele a la agencia.")
            return redirect("content:solicitudes")
        asunto, texto, archivos, errores = _leer_formulario(request, con_asunto=True)
        if errores:
            for e in errores:
                messages.error(request, e)
        else:
            with transaction.atomic():
                solicitud = Solicitud.all_objects.create(cliente=cliente, asunto=asunto, creado_por=request.user)
                _guardar_mensaje(solicitud, request.user, texto, archivos)
            notificar(
                equipo_del_cliente(cliente),
                f"Nueva solicitud de {cliente.nombre}: {asunto}",
                texto[:300],
                url=reverse("content:panel_solicitud", args=[solicitud.pk]),
                request=request,
            )
            messages.success(request, "Solicitud enviada. La agencia te responderá por aquí y te llegará un aviso.")
            return redirect("content:solicitud", pk=solicitud.pk)

    solicitudes = _solicitudes_del_cliente(request).select_related("creado_por")
    return render(request, "content/solicitudes.html", contexto_portal(
        request, "solicitudes",
        solicitudes=solicitudes,
        extensiones=", ".join(sorted(e.lstrip(".").upper() for e in EXTENSIONES_SOLICITUD)),
        tamano_max=TAMANO_MAX_SOLICITUD_MB, max_archivos=MAX_ARCHIVOS_POR_MENSAJE,
    ))


@requiere_rol_cliente
def portal_solicitud(request, pk):
    from .views import _obtener_o_404, contexto_portal

    solicitud = _obtener_o_404(_solicitudes_del_cliente(request), pk)
    if request.method == "POST":
        if solicitud.estado == Solicitud.Estado.CERRADA:
            messages.error(request, "Esta solicitud está cerrada. Crea una nueva si necesitas algo más.")
            return redirect("content:solicitud", pk=solicitud.pk)
        _, texto, archivos, errores = _leer_formulario(request, con_asunto=False)
        if errores:
            for e in errores:
                messages.error(request, e)
        else:
            with transaction.atomic():
                _guardar_mensaje(solicitud, request.user, texto, archivos)
                solicitud.estado = Solicitud.Estado.ABIERTA
                solicitud.save(update_fields=["estado", "actualizado_en"])
            notificar(
                equipo_del_cliente(solicitud.cliente),
                f"Nuevo mensaje de {solicitud.cliente.nombre}: {solicitud.asunto}",
                texto[:300],
                url=reverse("content:panel_solicitud", args=[solicitud.pk]),
                request=request,
            )
            messages.success(request, "Mensaje enviado.")
            return redirect("content:solicitud", pk=solicitud.pk)
    return render(request, "content/solicitud_detalle.html", contexto_portal(
        request, "solicitudes",
        solicitud=solicitud, mensajes=_hilo(solicitud),
        tamano_max=TAMANO_MAX_SOLICITUD_MB, max_archivos=MAX_ARCHIVOS_POR_MENSAJE,
    ))


@requiere_rol_cliente
def portal_archivo(request, pk):
    from .views import _obtener_o_404

    archivo = _obtener_o_404(
        ArchivoSolicitud.objects.filter(mensaje__solicitud__in=_solicitudes_del_cliente(request)), pk
    )
    return _descargar(archivo)


# ── Panel de la agencia ─────────────────────────────────────────────────────

def _solicitudes_del_equipo(user):
    return Solicitud.all_objects.filter(cliente__in=clientes_visibles(user))


@requiere_equipo
def panel_solicitudes(request):
    from apps.crm.views import contexto_panel

    from .views import _entero

    clientes = clientes_visibles(request.user).order_by("nombre")
    # Filtro por cliente: el elegido en la página o, si no hay, el cliente activo del panel.
    parametro = request.GET.get("cliente")
    cliente_id = _entero(parametro) if parametro is not None else getattr(request, "client_id", None)
    cliente = clientes.filter(pk=cliente_id).first() if cliente_id else None

    base = _solicitudes_del_equipo(request.user)
    if cliente:
        base = base.filter(cliente=cliente)
    estado = request.GET.get("estado", "")
    if estado not in Solicitud.Estado.values:
        estado = ""
    solicitudes = base.filter(estado=estado) if estado else base
    conteo = {e: base.filter(estado=e).count() for e in Solicitud.Estado.values}
    return render(request, "content/panel_solicitudes.html", contexto_panel(
        request, "solicitudes",
        solicitudes=solicitudes.select_related("cliente", "creado_por"),
        estado=estado, estados=Solicitud.Estado.choices, conteo=conteo,
        clientes=clientes, cliente=cliente,
    ))


@requiere_equipo
def panel_solicitud(request, pk):
    from apps.crm.views import contexto_panel

    from .views import _obtener_o_404

    solicitud = _obtener_o_404(_solicitudes_del_equipo(request.user).select_related("cliente"), pk)
    if request.method == "POST":
        accion = request.POST.get("accion", "responder")
        if accion in ("cerrar", "reabrir"):
            solicitud.estado = Solicitud.Estado.CERRADA if accion == "cerrar" else Solicitud.Estado.ABIERTA
            solicitud.save(update_fields=["estado", "actualizado_en"])
            messages.success(request, "Solicitud cerrada." if accion == "cerrar" else "Solicitud reabierta.")
            return redirect("content:panel_solicitud", pk=solicitud.pk)
        _, texto, archivos, errores = _leer_formulario(request, con_asunto=False)
        if errores:
            for e in errores:
                messages.error(request, e)
        else:
            with transaction.atomic():
                _guardar_mensaje(solicitud, request.user, texto, archivos)
                solicitud.estado = Solicitud.Estado.RESPONDIDA
                solicitud.save(update_fields=["estado", "actualizado_en"])
            notificar(
                usuarios_del_cliente(solicitud.cliente),
                f"La agencia respondió tu solicitud: {solicitud.asunto}",
                texto[:300],
                url=reverse("content:solicitud", args=[solicitud.pk]),
                request=request,
            )
            messages.success(request, "Respuesta enviada. El cliente recibió un aviso.")
            return redirect("content:panel_solicitud", pk=solicitud.pk)
    return render(request, "content/panel_solicitud_detalle.html", contexto_panel(
        request, "solicitudes",
        solicitud=solicitud, mensajes=_hilo(solicitud),
        tamano_max=TAMANO_MAX_SOLICITUD_MB, max_archivos=MAX_ARCHIVOS_POR_MENSAJE,
    ))


@requiere_equipo
def panel_archivo(request, pk):
    from .views import _obtener_o_404

    archivo = _obtener_o_404(
        ArchivoSolicitud.objects.filter(mensaje__solicitud__in=_solicitudes_del_equipo(request.user)).select_related(
            "mensaje__solicitud__cliente"
        ),
        pk,
    )
    RegistroAuditoria.registrar(
        usuario=request.user, accion=RegistroAuditoria.Accion.DESCARGAR, entidad="archivo de solicitud",
        entidad_id=archivo.pk, detalle=f"{archivo.nombre} · {archivo.mensaje.solicitud.cliente.nombre}"[:255],
    )
    return _descargar(archivo)
