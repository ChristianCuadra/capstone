"""Portal del cliente y panel interno: calendario, aprobaciones y carga de contenido."""

import calendar
from datetime import date, timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.conf import settings
from apps.accounts.decorators import requiere_rol_cliente
from apps.accounts.models import Rol
from apps.clients.models import Cliente
from apps.content.models import PiezaContenido, EstadoPieza, ComentarioPieza, HistorialVersionPieza
from django.http import JsonResponse

import os
ESTADOS = EstadoPieza.choices
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
    
    # Aislamiento multi-tenant: Solo piezas del cliente autenticado
    if cliente:
        piezas_qs = PiezaContenido.objects.filter(
            cliente=cliente,
            fecha_programada__year=primero.year,
            fecha_programada__month=primero.month
        )
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
        estados=ESTADOS,
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

        pieza_id = request.POST.get("pieza_id")
        accion = request.POST.get("accion")
        comentario_texto = request.POST.get("comentario", "").strip()
        
        pieza = get_object_or_404(PiezaContenido, pk=pieza_id, cliente=cliente)
        
        if pieza.estado == EstadoPieza.APROBADO and accion == "aprobar":
            messages.warning(request, f"La publicación '{pieza.titulo}' ya se encuentra aprobada previamente.")
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
            if not comentario_texto:
                messages.error(request, "Debes escribir un comentario explicando los cambios o correcciones requeridas.")
                return redirect("content:aprobacion")

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
            notificar_agencia_solicitud_cambios(request, pieza, comentario_texto)

            messages.warning(request, f"Se han solicitado cambios para la pieza '{pieza.titulo}'.")

        elif accion == "comentar":
            if comentario_texto:
                ComentarioPieza.objects.create(pieza=pieza, usuario=request.user, comentario=comentario_texto)
                messages.success(request, "Comentario añadido al hilo de la publicación.")

        return redirect("content:aprobacion")

    ahora = timezone.now()
    if cliente:
        # 1. Pendientes de aprobación
        pendientes = PiezaContenido.objects.filter(
            cliente=cliente, 
            estado=EstadoPieza.EN_REVISION
        ).prefetch_related("comentarios__usuario", "historial_versiones").select_related("aprobado_por")
        
        # 2. Piezas ACTIVAS (Solo versión más reciente de publicaciones con fecha futura)
        piezas_activas = PiezaContenido.objects.filter(
            cliente=cliente,
            fecha_programada__gte=ahora
        ).exclude(estado=EstadoPieza.BORRADOR).order_by("fecha_programada").select_related("aprobado_por")

        # 3. REGISTRO HISTÓRICO COMPLETO (Incluye Borradores, pasadas y evaluadas)
        piezas_historico = PiezaContenido.objects.filter(
            cliente=cliente
        ).order_by("-actualizado_en").select_related("aprobado_por")
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

@login_required
def interna_calendario(request):
    user = request.user
    
    if user.rol == Rol.ADMINISTRADORA or user.is_superuser:
        clientes_disponibles = Cliente.objects.filter(activo=True)
    elif user.rol == Rol.COLABORADORA:
        clientes_disponibles = user.clientes_asignados.filter(activo=True)
    else:
        clientes_disponibles = Cliente.objects.none()

    cliente_id = request.GET.get("cliente_id")
    cliente_seleccionado = None
    if cliente_id:
        cliente_seleccionado = clientes_disponibles.filter(id=cliente_id).first()

    if cliente_seleccionado:
        base_piezas = PiezaContenido.objects.filter(cliente=cliente_seleccionado)
    else:
        base_piezas = PiezaContenido.objects.filter(cliente__in=clientes_disponibles)

    piezas_rechazadas = base_piezas.filter(
        estado=EstadoPieza.RECHAZADO
    ).prefetch_related("comentarios").order_by("-actualizado_en")

    piezas_generales = base_piezas.exclude(
        estado=EstadoPieza.RECHAZADO
    ).order_by("-fecha_programada")

    nombre_usuario = user.get_full_name() or user.username or user.email
    iniciales = "".join(p[0] for p in nombre_usuario.replace("@", " ").split()[:2]).upper()

    return render(
        request, 
        "content/interna_calendario.html", 
        {
            "clientes": clientes_disponibles,
            "cliente_seleccionado": cliente_seleccionado,
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
    usuarios_cliente = pieza.cliente.usuarios.filter(rol=Rol.CLIENTE_APROBADOR)
    destinatarios = [u.email for u in usuarios_cliente if u.email]
    
    if destinatarios:
        url_directa = request.build_absolute_uri("/portal/aprobaciones/")
        asunto = f"Nueva pieza pendiente de aprobación: {pieza.titulo}"
        mensaje = (
            f"Hola,\n\nSe ha cargado una nueva pieza de contenido para {pieza.cliente.nombre} "
            f"programada para {pieza.fecha_programada}.\n\n"
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

@login_required
def crear_pieza(request):
    if request.method == "POST":
        cliente_id = request.POST.get("cliente_id")
        user = request.user

        if user.rol == Rol.COLABORADORA and not user.clientes_asignados.filter(id=cliente_id).exists():
            messages.error(request, "No tienes permiso para cargar contenido en este cliente.")
            return redirect("content:interna_calendario")

        cliente = get_object_or_404(Cliente, id=cliente_id)

        pieza = PiezaContenido(
            cliente=cliente,
            titulo=request.POST.get("titulo"),
            texto=request.POST.get("texto"),
            red_social=request.POST.get("red_social"),
            estado=request.POST.get("estado", EstadoPieza.BORRADOR),
            fecha_programada=request.POST.get("fecha_programada"),
            archivo=request.FILES.get("archivo"),
            creado_por=user,
        )
        pieza.save()

        if pieza.estado == EstadoPieza.EN_REVISION:
            notificar_pieza_en_revision(request, pieza)

        messages.success(request, f"Pieza '{pieza.titulo}' guardada exitosamente.")
        return redirect("content:interna_calendario")

    return redirect("content:interna_calendario")

@login_required
def obtener_historial_pieza(request, pieza_id):
    """Endpoint AJAX que devuelve la versión actual viva + el historial de versiones anteriores."""
    pieza = get_object_or_404(PiezaContenido, pk=pieza_id)
    
    def resolver_url(archivo_obj):
        if not archivo_obj:
            return None
        if hasattr(archivo_obj, 'url'):
            try:
                return archivo_obj.url
            except Exception:
                pass
        ruta_str = str(archivo_obj).strip().replace('\\', '/')
        if ruta_str.startswith('/media/'):
            ruta_str = ruta_str[7:]
        elif ruta_str.startswith('media/'):
            ruta_str = ruta_str[6:]
        if ruta_str:
            media_base = settings.MEDIA_URL if settings.MEDIA_URL.endswith('/') else f"{settings.MEDIA_URL}/"
            return f"{media_base}{ruta_str.lstrip('/')}"
        return None

    # 1. Datos de la versión actual viva
    evaluador_actual = "—"
    if pieza.aprobado_por:
        evaluador_actual = pieza.aprobado_por.get_full_name() or pieza.aprobado_por.username

    version_actual_data = {
        "version": pieza.version,
        "titulo": pieza.titulo,
        "texto": pieza.texto or "Sin copy asignado",
        "red_social": pieza.get_red_social_display(),
        "estado": pieza.get_estado_display(),
        "fecha_programada": pieza.fecha_programada.strftime("%d-%m-%Y %H:%M") if pieza.fecha_programada else "—",
        "evaluado_por": evaluador_actual,
        "archivo": resolver_url(pieza.archivo)
    }

    # 2. Historial de versiones anteriores auditadas
    versiones_anteriores = []
    for h in pieza.historial_versiones.all().order_by("-version"):
        modificado_nombre = "—"
        if hasattr(h, 'modificado_por') and h.modificado_por:
            modificado_nombre = h.modificado_por.get_full_name() or h.modificado_por.username

        versiones_anteriores.append({
            "version": h.version,
            "titulo": h.titulo,
            "texto": h.texto,
            "archivo": resolver_url(h.archivo),
            "estado_al_guardar": h.get_estado_al_guardar_display() if hasattr(h, 'get_estado_al_guardar_display') else h.estado_al_guardar,
            "evaluado_por": modificado_nombre,
            "creado_en": h.creado_en.strftime("%d-%m-%Y %H:%M"),
        })

    return JsonResponse({
        "actual": version_actual_data,
        "historial": versiones_anteriores
    })

@login_required
def editar_pieza(request, pieza_id):
    user = request.user
    pieza = get_object_or_404(PiezaContenido, pk=pieza_id)

    if request.method == "POST":
        # Bloquear edición si la pieza ya se encuentra en estado APROBADO
        if pieza.estado == EstadoPieza.APROBADO:
            messages.error(
                request, 
                f"La pieza '{pieza.titulo}' ya está aprobada y no puede ser modificada. Para hacer cambios, crea una nueva publicación."
            )
            return redirect("content:interna_calendario")

        # 1. Guardar registro inmutable de la versión actual antes de editar
        HistorialVersionPieza.objects.create(
            pieza=pieza,
            version=pieza.version,
            titulo=pieza.titulo,
            texto=pieza.texto,
            archivo=pieza.archivo.name if pieza.archivo else None,
            estado_al_guardar=pieza.estado,
            modificado_por=user
        )

        # 2. Actualizar campos
        pieza.titulo = request.POST.get("titulo")
        pieza.texto = request.POST.get("texto")
        pieza.red_social = request.POST.get("red_social")
        pieza.fecha_programada = request.POST.get("fecha_programada")
        
        nuevo_estado = request.POST.get("estado")
        pieza.estado = nuevo_estado

        if request.FILES.get("archivo"):
            pieza.archivo = request.FILES.get("archivo")

        pieza.version += 1
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

    return redirect("content:interna_calendario")