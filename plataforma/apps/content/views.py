"""Portal del cliente y panel interno: calendario, aprobaciones y carga de contenido."""

import calendar
from datetime import date, timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from django.http import Http404, JsonResponse
from django.urls import reverse
from apps.accounts.activacion import Estado, estado_cuenta
from apps.accounts.decorators import requiere_equipo, requiere_rol_cliente
from apps.core.access import clientes_visibles
from apps.accounts.models import Rol
from apps.content.forms import PiezaForm
from apps.content.models import PiezaContenido, EstadoPieza, ComentarioPieza, HistorialVersionPieza

ESTADOS = EstadoPieza.choices
# Lo que ve el cliente: los borradores son solo internos y no aparecen en el portal.
ESTADOS_PORTAL = [(clave, nombre) for clave, nombre in ESTADOS if clave != EstadoPieza.BORRADOR]
ETIQUETAS_ESTADO = dict(ESTADOS)

# Estados que el equipo de la agencia puede asignar desde el panel. «Aprobado» queda fuera a propósito:
# solo el cliente aprobador aprueba desde el portal (PC-APR-01), y así la trazabilidad de PC-APR-02 no se puede saltar.
ESTADOS_AL_CREAR = {EstadoPieza.BORRADOR, EstadoPieza.EN_REVISION}
ESTADOS_AL_EDITAR = {EstadoPieza.BORRADOR, EstadoPieza.EN_REVISION, EstadoPieza.RECHAZADO}


def _piezas_visibles(user):
    """Piezas de los clientes que el usuario puede ver (misma regla que PC-AUT-04 / PC-AUT-05)."""
    return PiezaContenido.objects.filter(cliente__in=clientes_visibles(user))


def _clientes_del_panel(user):
    """Clientes activos en los que el usuario del equipo puede cargar piezas (misma regla que clientes_visibles)."""
    return clientes_visibles(user).filter(activo=True)


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _obtener_o_404(queryset, pk):
    """El objeto pedido o 404, también cuando el id llega mal escrito desde un formulario."""
    try:
        return queryset.get(pk=_entero(pk))
    except queryset.model.DoesNotExist as exc:
        raise Http404 from exc


def _fecha_local(valor):
    return timezone.localtime(valor).strftime("%d-%m-%Y %H:%M") if valor else "—"


MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]


# ==========================================
# 1. PORTAL DEL CLIENTE
# ==========================================

def contexto_portal(request, seccion, **context):
    """Datos comunes del layout del portal: aislamiento estricto por cliente. """
    u = request.user
    nombre = u.get_full_name() or u.email or u.username
    cliente = u.cliente

    context["portal_usuario"] = {
        "nombre": nombre,
        "iniciales": "".join(p[0] for p in nombre.replace("@", " ").split()[:2]).upper(),
    }
    context["portal_cliente"] = cliente

    # Contar aprobaciones pendientes del cliente logueado
    aprobaciones_pendientes = 0
    if cliente:
        aprobaciones_pendientes = PiezaContenido.objects.filter(
            cliente=cliente,
            estado=EstadoPieza.EN_REVISION
        ).count()

    context["portal_badges"] = {"aprobaciones": aprobaciones_pendientes}
    context["seccion_portal"] = seccion
    return context


def _mes_desde_parametro(valor, hoy):
    try:
        anio, mes = (int(x) for x in valor.split("-"))
        return date(anio, mes, 1)
    except (ValueError, AttributeError):
        return hoy.replace(day=1)


@requiere_rol_cliente
def calendario(request):
    """Calendario mensual del cliente."""
    hoy = timezone.localdate()
    primero = _mes_desde_parametro(request.GET.get("mes"), hoy)
    anterior = (primero - timedelta(days=1)).replace(day=1)
    siguiente = (primero + timedelta(days=32)).replace(day=1)

    cliente = request.user.cliente

    # Aislamiento multi-tenant: solo piezas del cliente autenticado, sin los borradores internos
    if cliente:
        piezas_qs = PiezaContenido.objects.filter(
            cliente=cliente,
            fecha_programada__year=primero.year,
            fecha_programada__month=primero.month
        ).exclude(estado=EstadoPieza.BORRADOR)
    else:
        piezas_qs = PiezaContenido.objects.none()

    # Formateo de fechas a la zona horaria local de Chile
    por_dia = {}
    for pieza in piezas_qs:
        fecha_local = timezone.localtime(pieza.fecha_programada).date()
        por_dia.setdefault(fecha_local, []).append(pieza)

    semanas = [
        [
            {
                "fecha": dia,
                "en_mes": dia.month == primero.month,
                "hoy": dia == hoy,
                "piezas": por_dia.get(dia, [])
            }
            for dia in semana
        ]
        for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(primero.year, primero.month)
    ]

    vista = "lista" if request.GET.get("vista") == "lista" else "mes"

    context = contexto_portal(
        request,
        "calendario",
        mes_nombre=MESES[primero.month - 1],
        anio=primero.year,
        mes_param=f"{primero.year}-{primero.month:02d}",
        mes_anterior=f"{anterior.year}-{anterior.month:02d}",
        mes_siguiente=f"{siguiente.year}-{siguiente.month:02d}",
        total_piezas=piezas_qs.count(),
        en_revision=piezas_qs.filter(estado=EstadoPieza.EN_REVISION).count(),
        vista=vista,
        estados=ESTADOS_PORTAL,
        dias_semana=["L", "M", "M", "J", "V", "S", "D"],
        semanas=semanas,
        dias_con_piezas=[{"fecha": f, "hoy": f == hoy, "piezas": por_dia[f]} for f in sorted(por_dia)],
    )
    return render(request, "content/calendario.html", context)


@requiere_rol_cliente
def aprobacion(request):
    """Gestión de aprobación/rechazo por parte del cliente."""
    cliente = request.user.cliente

    if request.method == "POST":
        if request.user.rol != Rol.CLIENTE_APROBADOR:
            messages.error(request, "Solo el usuario con rol 'Cliente Aprobador' puede aprobar o solicitar cambios en el contenido.")
            return redirect("content:aprobacion")

        accion = request.POST.get("accion")
        comentario_texto = request.POST.get("comentario", "").strip()

        if accion == "rechazar" and not comentario_texto:
            messages.error(request, "Debes escribir un comentario explicando los cambios o correcciones requeridas.")
            return redirect("content:aprobacion")

        with transaction.atomic():
            # Fila bloqueada: si la agencia edita la pieza al mismo tiempo, una de las dos acciones espera a la otra.
            # Los borradores son solo internos: el cliente no los ve ni puede actuar sobre ellos.
            piezas = PiezaContenido.objects.select_for_update().filter(cliente=cliente).exclude(estado=EstadoPieza.BORRADOR)
            pieza = _obtener_o_404(piezas, request.POST.get("pieza_id"))

            if accion in ("aprobar", "rechazar"):
                # Solo se evalúa lo que la agencia envió a revisión: una pieza aprobada no se puede reabrir desde aquí.
                if pieza.estado != EstadoPieza.EN_REVISION:
                    messages.warning(
                        request,
                        f"La publicación '{pieza.titulo}' ya no está en revisión ({pieza.get_estado_display()}).",
                    )
                    return redirect("content:aprobacion")
                # Se aprueba exactamente la versión que el cliente tenía en pantalla (PC-APR-02).
                if _entero(request.POST.get("version")) != pieza.version:
                    messages.warning(
                        request,
                        f"La publicación '{pieza.titulo}' cambió a la versión v{pieza.version} mientras la revisabas. "
                        "Revisa la nueva versión antes de decidir.",
                    )
                    return redirect("content:aprobacion")

            if accion == "aprobar":
                pieza.estado = EstadoPieza.APROBADO
                pieza.aprobado_por = request.user
                pieza.fecha_aprobacion = timezone.now()
                pieza.save(update_fields=["estado", "aprobado_por", "fecha_aprobacion", "actualizado_en"])

                # Crear snapshot inmutable de trazabilidad
                HistorialVersionPieza.objects.create(
                    pieza=pieza,
                    version=pieza.version,
                    titulo=pieza.titulo,
                    texto=pieza.texto,
                    archivo=pieza.archivo.name if pieza.archivo else None,
                    estado_al_guardar=EstadoPieza.APROBADO,
                    modificado_por=request.user
                )

                if comentario_texto:
                    ComentarioPieza.objects.create(pieza=pieza, usuario=request.user, comentario=comentario_texto)

                messages.success(request, f"Pieza '{pieza.titulo}' aprobada exitosamente.")

            elif accion == "rechazar":
                pieza.estado = EstadoPieza.RECHAZADO
                pieza.aprobado_por = request.user  # Guarda al evaluador que rechazó/pidió cambios
                pieza.save(update_fields=["estado", "aprobado_por", "actualizado_en"])

                HistorialVersionPieza.objects.create(
                    pieza=pieza,
                    version=pieza.version,
                    titulo=pieza.titulo,
                    texto=pieza.texto,
                    archivo=pieza.archivo.name if pieza.archivo else None,
                    estado_al_guardar=EstadoPieza.RECHAZADO,
                    modificado_por=request.user
                )

                ComentarioPieza.objects.create(pieza=pieza, usuario=request.user, comentario=comentario_texto)
                messages.warning(request, f"Se han solicitado cambios para la pieza '{pieza.titulo}'.")

            elif accion == "comentar":
                if comentario_texto:
                    ComentarioPieza.objects.create(pieza=pieza, usuario=request.user, comentario=comentario_texto)
                    messages.success(request, "Comentario añadido al hilo de la publicación.")

        if accion == "rechazar":
            notificar_agencia_solicitud_cambios(request, pieza, comentario_texto)

        return redirect("content:aprobacion")

    ahora = timezone.now()
    if cliente:
        # Los borradores son solo internos: no aparecen en ninguna sección del portal.
        piezas_cliente = PiezaContenido.objects.filter(cliente=cliente).exclude(estado=EstadoPieza.BORRADOR)

        # 1. Pendientes de aprobación
        pendientes = piezas_cliente.filter(
            estado=EstadoPieza.EN_REVISION
        ).prefetch_related("comentarios__usuario", "historial_versiones").select_related("aprobado_por")

        # 2. Piezas ACTIVAS (Solo versión más reciente de publicaciones con fecha futura)
        piezas_activas = piezas_cliente.filter(
            fecha_programada__gte=ahora
        ).order_by("fecha_programada").select_related("aprobado_por")

        # 3. REGISTRO HISTÓRICO COMPLETO (pasadas y evaluadas)
        piezas_historico = piezas_cliente.order_by("-actualizado_en").select_related("aprobado_por")
    else:
        pendientes = PiezaContenido.objects.none()
        piezas_activas = PiezaContenido.objects.none()
        piezas_historico = PiezaContenido.objects.none()

    context = contexto_portal(
        request,
        "aprobaciones",
        pendientes=pendientes,
        piezas_activas=piezas_activas,
        revisadas=piezas_historico
    )
    return render(request, "content/aprobacion.html", context)

def notificar_agencia_solicitud_cambios(request, pieza, comentario):
    """Notifica al creador o equipo de la agencia cuando se solicitan cambios."""
    destinatarios = []
    if pieza.creado_por and pieza.creado_por.email:
        destinatarios.append(pieza.creado_por.email)

    if destinatarios:
        asunto = f"Cambios solicitados en pieza: {pieza.titulo} ({pieza.cliente.nombre})"
        mensaje = (
            f"El cliente {request.user.get_full_name() or request.user.username} ha solicitado cambios en la pieza '{pieza.titulo}'.\n\n"
            f"Observaciones:\n\"{comentario}\"\n\n"
            f"Puedes ingresar al panel interno para realizar las correcciones necesarias."
        )
        try:
            send_mail(asunto, mensaje, settings.DEFAULT_FROM_EMAIL, destinatarios, fail_silently=True)
        except Exception:
            pass

@requiere_rol_cliente
def metricas(request):
    context = contexto_portal(request, "metricas", hay_datos=False)
    return render(request, "content/metricas.html", context)


# ==========================================
# 2. PANEL INTERNO / COLABORADORAS
# ==========================================

@requiere_equipo
def interna_calendario(request):
    user = request.user
    clientes_disponibles = _clientes_del_panel(user)

    cliente_id = _entero(request.GET.get("cliente_id"))
    cliente_seleccionado = None
    if cliente_id:
        cliente_seleccionado = clientes_disponibles.filter(id=cliente_id).first()

    if cliente_seleccionado:
        base_piezas = PiezaContenido.objects.filter(cliente=cliente_seleccionado)
    else:
        base_piezas = PiezaContenido.objects.filter(cliente__in=clientes_disponibles)

    estado_seleccionado = request.GET.get("estado", "")
    if estado_seleccionado in EstadoPieza.values:
        base_piezas = base_piezas.filter(estado=estado_seleccionado)
    else:
        estado_seleccionado = ""

    piezas_rechazadas = list(
        base_piezas.filter(estado=EstadoPieza.RECHAZADO)
        .select_related("cliente")
        .prefetch_related("comentarios__usuario")
        .order_by("-actualizado_en")
    )
    for pieza in piezas_rechazadas:
        # Última observación del cliente: el hilo también guarda las respuestas de la agencia.
        pieza.observacion_cliente = next((c for c in reversed(pieza.comentarios.all()) if c.usuario.es_cliente), None)

    piezas_generales = base_piezas.exclude(
        estado=EstadoPieza.RECHAZADO
    ).select_related("cliente").order_by("-fecha_programada")

    nombre_usuario = user.get_full_name() or user.username or user.email
    iniciales = "".join(p[0] for p in nombre_usuario.replace("@", " ").split()[:2]).upper()

    return render(
        request,
        "content/interna_calendario.html",
        {
            "clientes": clientes_disponibles,
            "cliente_seleccionado": cliente_seleccionado,
            "estado_seleccionado": estado_seleccionado,
            "piezas": piezas_generales,
            "piezas_rechazadas": piezas_rechazadas,
            "estados": EstadoPieza.choices,
            "seccion_panel": "calendario",
            "panel_usuario": {
                "nombre": nombre_usuario,
                "iniciales": iniciales,
                "cargo": user.get_rol_display() if hasattr(user, "get_rol_display") else "Usuario",
            },
        }
    )

def notificar_pieza_en_revision(request, pieza):
    usuarios_cliente = pieza.cliente.usuarios.filter(rol=Rol.CLIENTE_APROBADOR, is_active=True)
    # Solo cuentas activadas: una invitada todavía no puede iniciar sesión para revisar.
    destinatarios = [u.email for u in usuarios_cliente if u.email and estado_cuenta(u) == Estado.ACTIVA]

    if destinatarios:
        url_directa = request.build_absolute_uri(reverse("content:aprobacion"))
        asunto = f"Nueva pieza pendiente de aprobación: {pieza.titulo}"
        mensaje = (
            f"Hola,\n\nSe ha cargado una nueva pieza de contenido para {pieza.cliente.nombre} "
            f"programada para el {_fecha_local(pieza.fecha_programada)}.\n\n"
            f"Puedes revisar y aprobarla directamente en el portal:\n{url_directa}\n\n"
            f"Saludos,\nAgencia Cosmopolitan"
        )
        try:
            send_mail(
                asunto,
                mensaje,
                settings.DEFAULT_FROM_EMAIL,
                destinatarios,
                fail_silently=True
            )
        except Exception:
            pass

@requiere_equipo
def crear_pieza(request):
    if request.method == "POST":
        user = request.user
        # 404 si el cliente no existe o no es de los que el usuario puede ver (colaboradora: solo asignados).
        cliente = _obtener_o_404(_clientes_del_panel(user), request.POST.get("cliente_id"))

        estado = request.POST.get("estado", EstadoPieza.BORRADOR)
        if estado not in ESTADOS_AL_CREAR:
            messages.error(request, "Al crear una pieza solo se puede guardar como Borrador o enviarla a En revisión.")
            return redirect("content:interna_calendario")

        form = PiezaForm(
            request.POST, request.FILES, instance=PiezaContenido(cliente=cliente, estado=estado, creado_por=user)
        )
        if not form.is_valid():
            messages.error(request, f"No se pudo guardar la pieza. {form.errores_texto()}")
            return redirect("content:interna_calendario")
        pieza = form.save()

        if pieza.estado == EstadoPieza.EN_REVISION:
            notificar_pieza_en_revision(request, pieza)

        messages.success(request, f"Pieza '{pieza.titulo}' guardada exitosamente.")
        return redirect("content:interna_calendario")

    return redirect("content:interna_calendario")

@login_required
def obtener_historial_pieza(request, pieza_id):
    """Endpoint AJAX que devuelve la versión actual viva + el historial de versiones anteriores.

    Lo usan el panel (equipo) y el portal (cliente): cada uno solo ve piezas de sus clientes visibles,
    y un cliente nunca ve una pieza en Borrador ni versiones guardadas como borrador (son solo internas).
    """
    piezas = _piezas_visibles(request.user)
    historial = HistorialVersionPieza.objects.select_related("modificado_por").order_by("-version", "-creado_en")
    if request.user.es_cliente:
        piezas = piezas.exclude(estado=EstadoPieza.BORRADOR)
        historial = historial.exclude(estado_al_guardar=EstadoPieza.BORRADOR)
    pieza = get_object_or_404(piezas.select_related("aprobado_por"), pk=pieza_id)

    def resolver_url(archivo):
        """URL del archivo en el almacenamiento configurado (bucket S3 de Supabase en producción, MEDIA en local).

        Sirve para el FieldFile de la versión actual y para el nombre guardado en el historial.
        """
        nombre = getattr(archivo, "name", archivo)
        if not nombre:
            return None
        try:
            return default_storage.url(nombre)
        except Exception:
            return None

    def nombre_de(usuario):
        return (usuario.get_full_name() or usuario.username) if usuario else "—"

    # 1. Datos de la versión actual viva
    version_actual_data = {
        "version": pieza.version,
        "titulo": pieza.titulo,
        "texto": pieza.texto or "Sin copy asignado",
        "red_social": pieza.get_red_social_display(),
        "estado": pieza.get_estado_display(),
        "fecha_programada": _fecha_local(pieza.fecha_programada),
        "evaluado_por": nombre_de(pieza.aprobado_por),
        "fecha_aprobacion": _fecha_local(pieza.fecha_aprobacion) if pieza.fecha_aprobacion else None,
        "archivo": resolver_url(pieza.archivo)
    }

    # 2. Versiones anteriores auditadas. La versión actual ya se muestra arriba (con su evaluación), así que su
    # registro de aprobación o rechazo no se repite en la lista.
    versiones_anteriores = [
        {
            "version": h.version,
            "titulo": h.titulo,
            "texto": h.texto,
            "archivo": resolver_url(h.archivo),
            "estado_al_guardar": ETIQUETAS_ESTADO.get(h.estado_al_guardar, h.estado_al_guardar),
            "evaluado_por": nombre_de(h.modificado_por),
            "creado_en": _fecha_local(h.creado_en),
        }
        for h in historial.filter(pieza=pieza).exclude(version=pieza.version)
    ]

    return JsonResponse({
        "actual": version_actual_data,
        "historial": versiones_anteriores
    })

@requiere_equipo
def editar_pieza(request, pieza_id):
    if request.method != "POST":
        return redirect("content:interna_calendario")

    user = request.user
    with transaction.atomic():
        # Fila bloqueada: si el cliente aprueba mientras se edita, la segunda acción ve el estado que dejó la primera.
        pieza = get_object_or_404(_piezas_visibles(user).select_for_update(), pk=pieza_id)

        # Bloquear edición si la pieza ya se encuentra en estado APROBADO
        if pieza.estado == EstadoPieza.APROBADO:
            messages.error(
                request,
                f"La pieza '{pieza.titulo}' ya está aprobada y no puede ser modificada. Para hacer cambios, crea una nueva publicación."
            )
            return redirect("content:interna_calendario")

        nuevo_estado = request.POST.get("estado")
        if nuevo_estado not in ESTADOS_AL_EDITAR:
            messages.error(
                request,
                "Estado no permitido. Solo el cliente aprobador puede aprobar una pieza desde su portal.",
            )
            return redirect("content:interna_calendario")

        # Datos de la versión actual, tomados antes de que el formulario los reemplace en la instancia.
        version_anterior = {
            "version": pieza.version,
            "titulo": pieza.titulo,
            "texto": pieza.texto,
            "archivo": pieza.archivo.name if pieza.archivo else None,
            "estado_al_guardar": pieza.estado,
        }

        form = PiezaForm(request.POST, request.FILES, instance=pieza)
        if not form.is_valid():
            messages.error(request, f"No se pudo guardar la pieza. {form.errores_texto()}")
            return redirect("content:interna_calendario")

        # 1. Guardar registro inmutable de la versión actual antes de editar. Cada versión queda una sola vez:
        # si el cliente ya la evaluó (pidió cambios), ese registro es el que la representa.
        if not pieza.historial_versiones.filter(version=pieza.version).exists():
            HistorialVersionPieza.objects.create(pieza=pieza, modificado_por=user, **version_anterior)

        # 2. Actualizar campos
        pieza = form.save(commit=False)
        pieza.estado = nuevo_estado
        pieza.version += 1
        # La evaluación anterior era de la versión vieja: la nueva queda sin evaluar hasta que el cliente decida.
        pieza.aprobado_por = None
        pieza.fecha_aprobacion = None
        pieza.save()

        respuesta_comentario = request.POST.get("respuesta_comentario", "").strip()
        if respuesta_comentario:
            ComentarioPieza.objects.create(
                pieza=pieza,
                usuario=user,
                comentario=f"[Respuesta Agencia v{pieza.version}]: {respuesta_comentario}"
            )

    if nuevo_estado == EstadoPieza.EN_REVISION:
        notificar_pieza_en_revision(request, pieza)

    messages.success(request, f"Pieza '{pieza.titulo}' actualizada exitosamente a la versión v{pieza.version}.")
    return redirect("content:interna_calendario")
