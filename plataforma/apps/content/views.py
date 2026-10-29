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
from apps.content.models import PiezaContenido, EstadoPieza

ESTADOS = EstadoPieza.choices
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio", 
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]


# ==========================================
# 1. PORTAL DEL CLIENTE (PC-POR-01)
# ==========================================

def contexto_portal(request, seccion, **context):
    """Datos comunes del layout del portal: aislamiento estricto por cliente (CP-038, CP-039)."""
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
    """Calendario mensual del cliente (PC-POR-01, PC-CAL-02, CP-038, CP-049)."""
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

    # Formateo de fechas a la zona horaria local de Chile (CP-049)
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
    """Gestión de aprobación/rechazo por parte del cliente (PC-POR-01, CP-040)."""
    cliente = request.user.cliente
    
    if request.method == "POST":
        if request.user.rol != Rol.CLIENTE_APROBADOR:
            messages.error(request, "Solo el usuario con rol 'Cliente Aprobador' puede aprobar o rechazar contenido.")
            return redirect("content:aprobacion")

        pieza_id = request.POST.get("pieza_id")
        accion = request.POST.get("accion")
        
        # Validar pertenencia de la pieza al cliente activo
        pieza = get_object_or_404(PiezaContenido, pk=pieza_id, cliente=cliente)
        
        if accion == "aprobar":
            pieza.estado = EstadoPieza.APROBADO
            pieza.save(update_fields=["estado", "actualizado_en"])
            messages.success(request, f"Pieza '{pieza.titulo}' aprobada exitosamente.")
        elif accion == "rechazar":
            pieza.estado = EstadoPieza.RECHAZADO
            pieza.save(update_fields=["estado", "actualizado_en"])
            messages.warning(request, f"Pieza '{pieza.titulo}' marcada como rechazada.")
            
        return redirect("content:aprobacion")

    if cliente:
        pendientes = PiezaContenido.objects.filter(cliente=cliente, estado=EstadoPieza.EN_REVISION)
        revisadas = PiezaContenido.objects.filter(cliente=cliente).exclude(estado=EstadoPieza.EN_REVISION)[:10]
    else:
        pendientes = PiezaContenido.objects.none()
        revisadas = PiezaContenido.objects.none()

    context = contexto_portal(request, "aprobaciones", pendientes=pendientes, revisadas=revisadas)
    return render(request, "content/aprobacion.html", context)


@requiere_rol_cliente
def metricas(request):
    context = contexto_portal(request, "metricas", hay_datos=False)
    return render(request, "content/metricas.html", context)


# ==========================================
# 2. PANEL INTERNO / COLABORADORAS (PC-CAL-01, PC-CAL-02)
# ==========================================

@login_required
def interna_calendario(request):
    user = request.user
    
    # Filtrar clientes según permisos de la colaboradora o administradora
    if user.rol == Rol.ADMINISTRADORA or user.is_superuser:
        clientes_disponibles = Cliente.objects.filter(activo=True)
    elif user.rol == Rol.COLABORADORA:
        clientes_disponibles = user.clientes_asignados.filter(activo=True)
    else:
        clientes_disponibles = Cliente.objects.none()

    # Filtro por cliente seleccionado
    cliente_id = request.GET.get("cliente_id")
    cliente_seleccionado = None
    if cliente_id:
        cliente_seleccionado = clientes_disponibles.filter(id=cliente_id).first()

    if cliente_seleccionado:
        piezas = PiezaContenido.objects.filter(cliente=cliente_seleccionado)
    else:
        piezas = PiezaContenido.objects.filter(cliente__in=clientes_disponibles)

    # Construir datos para el footer del sidebar (base_panel.html)
    nombre_usuario = user.get_full_name() or user.username or user.email
    iniciales = "".join(p[0] for p in nombre_usuario.replace("@", " ").split()[:2]).upper()

    return render(
        request, 
        "content/interna_calendario.html", 
        {
            "clientes": clientes_disponibles,
            "cliente_seleccionado": cliente_seleccionado,
            "piezas": piezas,
            "estados": EstadoPieza.choices,
            "seccion_panel": "calendario",
            # Datos requeridos por base_panel.html para el usuario en sesión
            "panel_usuario": {
                "nombre": nombre_usuario,
                "iniciales": iniciales,
                "cargo": user.get_rol_display() if hasattr(user, "get_rol_display") else "Usuario",
            },
        }
    )

def notificar_pieza_en_revision(request, pieza):
    """Envía notificación por correo al cliente aprobador con enlace directo (CP-050)."""
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
    """Carga de piezas por colaboradora y envío a revisión (PC-CAL-01, CP-046, CP-050)."""
    if request.method == "POST":
        cliente_id = request.POST.get("cliente_id")
        user = request.user

        # Validar asignación de la colaboradora
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
            archivo=request.FILES.get("archivo"),  # Recibe imagen o video
            creado_por=user,
        )
        pieza.save()

        # Notificación automática al cliente cuando pasa a revisión (CP-050)
        if pieza.estado == EstadoPieza.EN_REVISION:
            notificar_pieza_en_revision(request, pieza)

        messages.success(request, f"Pieza '{pieza.titulo}' guardada exitosamente.")
        return redirect("content:interna_calendario")

    return redirect("content:interna_calendario")