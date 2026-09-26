"""Panel interno de la agencia (CRM comercial). Solo para el equipo (usuarios staff).

Todo sale de la base: prospectos, interacciones, cotizaciones, tareas y clientes.
Sin datos, cada bloque muestra su estado vacío (no hay datos de ejemplo).
"""

import csv
from datetime import date, timedelta

from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts.decorators import requiere_administradora
from apps.accounts.forms import UsuarioForm
from apps.accounts.models import Rol
from apps.ai.services import ErrorIA, IANoConfigurada, generar_diagnostico_cotizacion, reescribir_texto
from apps.catalog.models import Plan, Servicio
from apps.clients.models import Cliente
from apps.core.models import RegistroAuditoria
from allauth.mfa.models import Authenticator

from .models import Cotizacion, CotizacionItem, Interaccion, Prospecto, Tarea

ETAPAS_EMBUDO = [
    Prospecto.Etapa.NUEVO,
    Prospecto.Etapa.CONTACTADO,
    Prospecto.Etapa.REUNION,
    Prospecto.Etapa.COTIZACION_ENVIADA,
    Prospecto.Etapa.GANADO,
]
ETAPAS_ACTIVAS = ETAPAS_EMBUDO[:-1]
PERIODOS = [("mes", "Este mes"), ("mes_anterior", "Mes anterior"), ("3_meses", "Últimos 3 meses"), ("anio", "Este año")]
MESES_CORTOS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

solo_equipo = user_passes_test(lambda u: u.is_active and u.is_staff, login_url="account_login")


# ── Utilidades ────────────────────────────────────────────────────────────────

def _nombre(usuario):
    return (usuario.get_full_name() or usuario.email or usuario.username) if usuario else None


def _iniciales(usuario):
    partes = _nombre(usuario).replace("@", " ").replace(".", " ").split()
    return "".join(p[0] for p in partes[:2]).upper()


def _equipo():
    return get_user_model().objects.filter(is_staff=True, is_active=True).order_by("first_name", "email")


def _volver(request, por_defecto):
    destino = request.POST.get("next") or request.GET.get("next")
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return redirect(destino)
    return redirect(por_defecto)


def _rango_periodo(clave, hoy):
    """(inicio, fin) del período, fin exclusivo."""
    inicio_mes = hoy.replace(day=1)
    siguiente_mes = (inicio_mes + timedelta(days=32)).replace(day=1)
    if clave == "mes_anterior":
        anterior = (inicio_mes - timedelta(days=1)).replace(day=1)
        return anterior, inicio_mes
    if clave == "3_meses":
        inicio = inicio_mes
        for _ in range(2):
            inicio = (inicio - timedelta(days=1)).replace(day=1)
        return inicio, siguiente_mes
    if clave == "anio":
        return date(hoy.year, 1, 1), date(hoy.year + 1, 1, 1)
    return inicio_mes, siguiente_mes


def _en_rango(momento, inicio, fin):
    return momento is not None and inicio <= timezone.localtime(momento).date() < fin


def contexto_panel(request, seccion, **context):
    """Datos comunes del layout del panel: usuario, badges del sidebar y sección activa."""
    u = request.user
    context["panel_usuario"] = {
        "nombre": _nombre(u),
        "cargo": u.get_rol_display() if u.rol else ("Administradora" if u.is_superuser else "Equipo"),
        "iniciales": _iniciales(u),
    }
    context["panel_badges"] = {"prospectos": Prospecto.objects.filter(etapa=Prospecto.Etapa.NUEVO).count()}
    context["seccion_panel"] = seccion
    return context


def _fila_prospecto(p):
    return {
        "id": p.pk,
        "empresa": p.empresa,
        "nombre": p.nombre,
        "detalle": f"{p.rubro} · {p.region}",
        "etapa": p.etapa,
        "etapa_nombre": p.get_etapa_display(),
        "valor_mensual": p.valor_estimado,
        "plan": p.plan_referencia.nombre if p.plan_referencia else None,
        "responsable": _nombre(p.responsable),
        "dias": p.dias_sin_movimiento,
        "creado_en": p.creado_en,
    }


# ── Dashboard ─────────────────────────────────────────────────────────────────

@solo_equipo
def dashboard(request):
    hoy = timezone.localdate()
    periodo = request.GET.get("periodo") if request.GET.get("periodo") in dict(PERIODOS) else "mes"
    inicio, fin = _rango_periodo(periodo, hoy)
    largo = fin - inicio
    inicio_prev, fin_prev = inicio - largo, inicio

    prospectos = list(Prospecto.objects.select_related("plan_sugerido", "plan_interes", "responsable"))
    cotizaciones = list(Cotizacion.objects.prefetch_related("items"))
    for c in cotizaciones:
        c.t = c.totales()

    # KPIs desde cotizaciones del período.
    def aceptadas_en(a, b):
        return [c for c in cotizaciones if c.estado == Cotizacion.Estado.ACEPTADA and _en_rango(c.respondida_en, a, b)]

    aceptadas = aceptadas_en(inicio, fin)
    rechazadas = [c for c in cotizaciones if c.estado == Cotizacion.Estado.RECHAZADA and _en_rango(c.respondida_en, inicio, fin)]
    enviadas = [c for c in cotizaciones if _en_rango(c.enviada_en, inicio, fin)]
    ingreso = sum(c.t["mensual"] for c in aceptadas)
    ingreso_prev = sum(c.t["mensual"] for c in aceptadas_en(inicio_prev, fin_prev))
    respondidas = len(aceptadas) + len(rechazadas)
    kpis = {
        "ingresos": {
            "valor": ingreso,
            "variacion_pct": round((ingreso - ingreso_prev) / ingreso_prev * 100, 1) if ingreso_prev else None,
        },
        "cotizaciones": {"cantidad": len(enviadas), "monto": sum(c.t["total"] for c in enviadas)},
        "cierre": {
            "tasa_pct": round(len(aceptadas) / respondidas * 100) if respondidas else None,
            "aceptadas": len(aceptadas),
            "rechazadas": len(rechazadas),
            "en_espera": sum(1 for c in cotizaciones if c.estado == Cotizacion.Estado.ENVIADA),
        },
        "ticket": {"valor": round(ingreso / len(aceptadas)) if aceptadas else None},
    }

    # Gráfico: últimos 6 meses, cotizaciones enviadas vs. aceptadas.
    meses = []
    mes = hoy.replace(day=1)
    for _ in range(6):
        meses.insert(0, mes)
        mes = (mes - timedelta(days=1)).replace(day=1)
    grafico = {"meses": [], "enviadas": [], "aceptadas": []}
    for m in meses:
        siguiente = (m + timedelta(days=32)).replace(day=1)
        grafico["meses"].append(MESES_CORTOS[m.month - 1])
        grafico["enviadas"].append(sum(1 for c in cotizaciones if _en_rango(c.enviada_en, m, siguiente)))
        grafico["aceptadas"].append(len(aceptadas_en(m, siguiente)))
    hay_grafico = any(grafico["enviadas"]) or any(grafico["aceptadas"])

    # Embudo: estado actual de todos los prospectos.
    embudo = []
    for etapa in ETAPAS_EMBUDO:
        de_la_etapa = [p for p in prospectos if p.etapa == etapa]
        embudo.append({
            "etapa": etapa.value, "nombre": etapa.label, "cantidad": len(de_la_etapa),
            "monto": sum(p.valor_estimado or 0 for p in de_la_etapa),
        })
    maximo = max(f["cantidad"] for f in embudo) or 1
    for fila in embudo:
        fila["ancho_pct"] = round(fila["cantidad"] / maximo * 100)

    # Origen de los prospectos del período: 3 principales + "Otros" (paleta validada de 4 colores).
    del_periodo = [p for p in prospectos if _en_rango(p.creado_en, inicio, fin)]
    conteo = {}
    for p in del_periodo:
        clave = p.get_como_nos_conocio_display() or "No indicó"
        conteo[clave] = conteo.get(clave, 0) + 1
    orden = sorted(conteo.items(), key=lambda x: -x[1])
    origenes = [{"origen": n, "cantidad": c} for n, c in orden[:3]]
    if len(orden) > 3:
        origenes.append({"origen": "Otros", "cantidad": sum(c for _, c in orden[3:])})
    for o in origenes:
        o["pct"] = round(o["cantidad"] / len(del_periodo) * 100)

    requieren_accion = sorted((p for p in prospectos if p.etapa in ETAPAS_ACTIVAS), key=lambda p: p.actualizado_en)[:5]
    tareas = Tarea.objects.select_related("responsable", "prospecto").filter(completada=False)[:8]

    context = contexto_panel(
        request,
        "dashboard",
        fecha_hoy=hoy,
        periodos=PERIODOS,
        periodo_actual=periodo,
        periodo_nombre=dict(PERIODOS)[periodo],
        kpis=kpis,
        embudo=embudo,
        hay_prospectos=bool(prospectos),
        grafico_cotizaciones=grafico,
        hay_grafico=hay_grafico,
        tabla_cotizaciones=[
            {"mes": m, "enviadas": e, "aceptadas": a}
            for m, e, a in zip(grafico["meses"], grafico["enviadas"], grafico["aceptadas"])
        ],
        prospectos_accion=[_fila_prospecto(p) for p in requieren_accion],
        dias_alerta=3,  # el Alcance compromete cotizar en 3 días hábiles
        tareas=[
            {
                "id": t.pk, "titulo": t.titulo, "fecha": t.fecha, "vencida": bool(t.fecha and t.fecha < hoy),
                "es_hoy": t.fecha == hoy, "responsable": _iniciales(t.responsable) if t.responsable else None,
                "responsable_nombre": _nombre(t.responsable), "prospecto": t.prospecto,
            }
            for t in tareas
        ],
        equipo=_equipo(),
        origenes=origenes,
    )
    return render(request, "crm/dashboard.html", context)


# ── Tareas ────────────────────────────────────────────────────────────────────

@solo_equipo
@require_POST
def tarea_crear(request):
    titulo = request.POST.get("titulo", "").strip()
    if not titulo:
        messages.error(request, "Escribe un título para la tarea.")
        return _volver(request, "crm:dashboard")
    responsable = _equipo().filter(pk=request.POST.get("responsable") or None).first()
    prospecto = Prospecto.objects.filter(pk=request.POST.get("prospecto") or None).first()
    try:
        fecha = date.fromisoformat(request.POST.get("fecha", ""))
    except ValueError:
        fecha = None
    Tarea.objects.create(titulo=titulo[:160], fecha=fecha, responsable=responsable, prospecto=prospecto, creado_por=request.user)
    messages.success(request, "Tarea creada.")
    return _volver(request, "crm:dashboard")


@solo_equipo
@require_POST
def tarea_alternar(request, pk):
    tarea = get_object_or_404(Tarea, pk=pk)
    tarea.completada = not tarea.completada
    tarea.completada_en = timezone.now() if tarea.completada else None
    tarea.save(update_fields=["completada", "completada_en"])
    return _volver(request, "crm:dashboard")


# ── Prospectos ────────────────────────────────────────────────────────────────

def _prospectos_filtrados(request):
    lista = Prospecto.objects.select_related("plan_sugerido", "plan_interes", "responsable")
    etapa = request.GET.get("etapa", "")
    if etapa in Prospecto.Etapa.values:
        lista = lista.filter(etapa=etapa)
    return lista, etapa


@solo_equipo
def prospectos(request):
    lista, etapa = _prospectos_filtrados(request)
    context = contexto_panel(
        request,
        "prospectos",
        prospectos=[_fila_prospecto(p) for p in lista],
        etapas=Prospecto.Etapa.choices,
        etapa_activa=etapa,
        total=Prospecto.objects.count(),
    )
    return render(request, "crm/prospectos.html", context)


@solo_equipo
def prospectos_exportar(request):
    lista, etapa = _prospectos_filtrados(request)
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="prospectos-{timezone.localdate().isoformat()}.csv"'
    respuesta.write("﻿")  # BOM para que Excel lea bien los acentos
    escritor = csv.writer(respuesta, delimiter=";")
    escritor.writerow([
        "Empresa", "Nombre", "Correo", "Teléfono", "Rubro", "Región", "Tamaño", "Presupuesto", "Objetivos",
        "Plan de interés", "Plan sugerido", "Etapa", "Responsable", "Cómo nos conoció", "Creado",
    ])
    for p in lista:
        escritor.writerow([
            p.empresa, p.nombre, p.correo, p.telefono, p.rubro, p.region, p.get_tamano_display(), p.get_presupuesto_display(),
            ", ".join(p.objetivos), p.plan_interes.nombre if p.plan_interes else "", p.plan_sugerido.nombre if p.plan_sugerido else "",
            p.get_etapa_display(), _nombre(p.responsable) or "", p.get_como_nos_conocio_display(),
            timezone.localtime(p.creado_en).strftime("%d-%m-%Y %H:%M"),
        ])
    return respuesta


@solo_equipo
def prospecto_detalle(request, pk):
    prospecto = get_object_or_404(
        Prospecto.objects.select_related("plan_sugerido", "plan_interes", "responsable", "diagnostico_revisado_por", "cliente"),
        pk=pk,
    )

    if request.method == "POST":
        _accion_prospecto(request, prospecto)
        return redirect(request.get_full_path())

    indice_actual = ETAPAS_EMBUDO.index(prospecto.etapa) if prospecto.etapa in ETAPAS_EMBUDO else -1
    progreso_embudo = [
        {"nombre": etapa.label, "estado": "completada" if i < indice_actual else "actual" if i == indice_actual else "pendiente"}
        for i, etapa in enumerate(ETAPAS_EMBUDO)
    ]

    filtros = [("todo", "Todo"), ("correo", "Correos"), ("llamada", "Llamadas"), ("reunion", "Reuniones")]
    filtro = request.GET.get("tipo", "todo")
    interacciones = prospecto.interacciones.select_related("autor")
    if filtro in Interaccion.Tipo.values:
        interacciones = interacciones.filter(tipo=filtro)

    tab = "cotizaciones" if request.GET.get("tab") == "cotizaciones" else "resumen"
    cotizaciones = list(prospecto.cotizaciones.prefetch_related("items"))
    for c in cotizaciones:
        c.t = c.totales()

    context = contexto_panel(
        request,
        "prospectos",
        prospecto=prospecto,
        progreso_embudo=progreso_embudo,
        interacciones=interacciones,
        filtros=filtros,
        filtro_activo=filtro,
        tab=tab,
        cotizaciones=cotizaciones,
        etapas=Prospecto.Etapa.choices,
        tipos_interaccion=[t for t in Interaccion.Tipo.choices if t[0] != Interaccion.Tipo.SISTEMA],
        ia_configurada=bool(settings.AI_API_KEY),
    )
    return render(request, "crm/prospecto_detalle.html", context)


def _registrar(prospecto, usuario, titulo, tipo=Interaccion.Tipo.SISTEMA, descripcion=""):
    Interaccion.objects.create(prospecto=prospecto, tipo=tipo, titulo=titulo[:160], descripcion=descripcion, autor=usuario)


def _mover_etapa(prospecto, nueva, usuario):
    if nueva == prospecto.etapa:
        return False
    anterior = prospecto.get_etapa_display()
    prospecto.etapa = nueva
    prospecto.save(update_fields=["etapa", "actualizado_en"])
    _registrar(prospecto, usuario, f"Etapa: {anterior} → {prospecto.get_etapa_display()}")
    return True


def _accion_prospecto(request, prospecto):
    accion = request.POST.get("accion")
    usuario = request.user

    if accion == "generar_diagnostico":
        try:
            generar_diagnostico_cotizacion(prospecto, usuario)
            messages.success(request, "Borrador de diagnóstico generado. Revísalo y edítalo antes de usarlo.")
        except IANoConfigurada:
            messages.error(request, "La IA no está configurada: falta AI_API_KEY en el archivo .env.")
        except ErrorIA as e:
            messages.error(request, f"No se pudo generar el diagnóstico. {e}")

    elif accion == "guardar_diagnostico":
        prospecto.diagnostico_ia = request.POST.get("diagnostico", "").strip()
        prospecto.diagnostico_revisado_por = usuario
        prospecto.diagnostico_revisado_en = timezone.now()
        prospecto.save(update_fields=["diagnostico_ia", "diagnostico_revisado_por", "diagnostico_revisado_en", "actualizado_en"])
        messages.success(request, "Diagnóstico guardado y marcado como revisado.")

    elif accion == "cambiar_etapa":
        nueva = request.POST.get("etapa")
        if nueva in Prospecto.Etapa.values and _mover_etapa(prospecto, nueva, usuario):
            messages.success(request, f"Prospecto movido a «{prospecto.get_etapa_display()}».")

    elif accion == "asignarme":
        prospecto.responsable = usuario
        prospecto.save(update_fields=["responsable", "actualizado_en"])
        messages.success(request, "Quedaste como responsable de este prospecto.")

    elif accion == "instagram":
        prospecto.instagram = request.POST.get("instagram", "").strip().lstrip("@")[:60]
        seguidores = request.POST.get("seguidores", "").replace(".", "").strip()
        prospecto.instagram_seguidores = int(seguidores) if seguidores.isdigit() else None
        prospecto.save(update_fields=["instagram", "instagram_seguidores", "actualizado_en"])
        messages.success(request, "Cuenta de Instagram actualizada.")

    elif accion == "registrar_interaccion":
        tipo = request.POST.get("tipo")
        titulo = request.POST.get("titulo", "").strip()
        if tipo in Interaccion.Tipo.values and titulo:
            _registrar(prospecto, usuario, titulo, tipo, request.POST.get("descripcion", "").strip())
            prospecto.save(update_fields=["actualizado_en"])
            messages.success(request, "Interacción registrada.")
        else:
            messages.error(request, "Indica el tipo y un título para la interacción.")

    elif accion == "convertir_cliente":
        if prospecto.cliente:
            messages.info(request, "Este prospecto ya es cliente.")
        else:
            prospecto.cliente = Cliente.objects.create(nombre=prospecto.empresa)
            prospecto.save(update_fields=["cliente", "actualizado_en"])
            _mover_etapa(prospecto, Prospecto.Etapa.GANADO, usuario)
            _registrar(prospecto, usuario, "Convertido en cliente")
            messages.success(request, f"{prospecto.empresa} ahora es cliente.")


# ── Cotizaciones ──────────────────────────────────────────────────────────────

@solo_equipo
def cotizaciones(request):
    lista = list(Cotizacion.objects.select_related("prospecto").prefetch_related("items"))
    for c in lista:
        c.t = c.totales()
    return render(request, "crm/cotizaciones.html", contexto_panel(request, "cotizaciones", cotizaciones=lista))


@solo_equipo
def cotizacion_nueva(request):
    """GET: elegir prospecto. POST: crea el borrador con el plan y servicios del prospecto y abre el editor."""
    if request.method == "POST":
        prospecto = get_object_or_404(Prospecto, pk=request.POST.get("prospecto") or 0)
        hoy = timezone.localdate()
        cotizacion = Cotizacion.objects.create(
            prospecto=prospecto,
            contacto=f"{prospecto.nombre} · {prospecto.correo}",
            valida_hasta=hoy + timedelta(days=15),
            inicio_estimado=(hoy.replace(day=1) + timedelta(days=32)).replace(day=1),
            diagnostico=prospecto.diagnostico_ia,
            creado_por=request.user,
        )
        if prospecto.plan_referencia:
            _agregar_plan(cotizacion, prospecto.plan_referencia)
        for servicio in prospecto.servicios_requeridos.all():
            _agregar_servicio(cotizacion, servicio)
        _registrar(prospecto, request.user, f"Cotización #{cotizacion.numero} creada (borrador)")
        return redirect("crm:cotizacion_editar", pk=cotizacion.pk)

    context = contexto_panel(
        request,
        "cotizaciones",
        prospectos_opciones=Prospecto.objects.exclude(etapa__in=[Prospecto.Etapa.GANADO, Prospecto.Etapa.PERDIDO]),
        prospecto_inicial=request.GET.get("prospecto", ""),
    )
    return render(request, "crm/cotizacion_nueva.html", context)


def _siguiente_orden(cotizacion):
    return (cotizacion.items.order_by("-orden").values_list("orden", flat=True).first() or 0) + 1


def _agregar_plan(cotizacion, plan):
    CotizacionItem.objects.create(
        cotizacion=cotizacion, plan=plan, descripcion=f"Plan {plan.nombre}", detalle=plan.descripcion[:255],
        valor_unitario=plan.precio_mensual, meses=6, orden=_siguiente_orden(cotizacion),
    )
    if plan.precio_primer_mes and plan.precio_primer_mes > plan.precio_mensual:
        CotizacionItem.objects.create(
            cotizacion=cotizacion, plan=plan, descripcion="Diferencia primer mes", detalle=f"Primer mes del plan {plan.nombre}",
            valor_unitario=plan.precio_primer_mes - plan.precio_mensual, meses=None, orden=_siguiente_orden(cotizacion),
        )


def _agregar_servicio(cotizacion, servicio):
    CotizacionItem.objects.create(
        cotizacion=cotizacion, servicio=servicio, descripcion=servicio.nombre, detalle=servicio.get_modalidad_cobro_display(),
        valor_unitario=servicio.precio, meses=6 if servicio.modalidad_cobro == Servicio.ModalidadCobro.MENSUAL else None,
        orden=_siguiente_orden(cotizacion),
    )


def _guardar_campos(request, cotizacion):
    """Guarda lo editado en el formulario (se ejecuta antes de cualquier otra acción para no perder cambios)."""
    cotizacion.contacto = request.POST.get("contacto", cotizacion.contacto)[:200]
    for campo in ("valida_hasta", "inicio_estimado"):
        try:
            setattr(cotizacion, campo, date.fromisoformat(request.POST.get(campo, "")))
        except ValueError:
            setattr(cotizacion, campo, None)
    if request.POST.get("forma_pago") in Cotizacion.FormaPago.values:
        cotizacion.forma_pago = request.POST["forma_pago"]
    if request.POST.get("descuento_pct", "").isdigit():
        cotizacion.descuento_pct = min(int(request.POST["descuento_pct"]), 50)
    cotizacion.diagnostico = request.POST.get("diagnostico", cotizacion.diagnostico).strip()
    cotizacion.save()
    for item in cotizacion.items.all():
        cantidad = request.POST.get(f"cantidad_{item.pk}", "")
        meses = request.POST.get(f"meses_{item.pk}", "")
        if cantidad.isdigit() and int(cantidad) > 0:
            item.cantidad = int(cantidad)
        if item.meses and meses.isdigit() and int(meses) > 0:
            item.meses = int(meses)
        item.save(update_fields=["cantidad", "meses"])


@solo_equipo
def cotizacion_editar(request, pk):
    cotizacion = get_object_or_404(Cotizacion.objects.select_related("prospecto"), pk=pk)
    prospecto = cotizacion.prospecto

    if request.method == "POST":
        # Cada botón envía "accion" o "accion:id" (p. ej. "mas:12"); así el formulario completo viaja con cualquier botón.
        accion, _, valor = request.POST.get("accion", "guardar").partition(":")
        if accion == "agregar_servicio":
            valor = valor or request.POST.get("servicio_agregar", "")
        elif accion == "agregar_plan":
            valor = valor or request.POST.get("plan_agregar", "")
        es_borrador = cotizacion.estado == Cotizacion.Estado.BORRADOR
        if es_borrador:
            _guardar_campos(request, cotizacion)

        if accion == "guardar" and es_borrador:
            messages.success(request, "Cambios guardados.")
        elif accion in ("mas", "menos", "quitar") and es_borrador:
            item = cotizacion.items.filter(pk=valor or 0).first()
            if item and accion == "quitar":
                item.delete()
            elif item:
                item.cantidad = max(1, item.cantidad + (1 if accion == "mas" else -1))
                item.save(update_fields=["cantidad"])
        elif accion == "agregar_servicio" and es_borrador:
            servicio = Servicio.objects.filter(pk=valor or 0, activo=True).first()
            if servicio:
                _agregar_servicio(cotizacion, servicio)
        elif accion == "agregar_plan" and es_borrador:
            plan = Plan.objects.filter(pk=valor or 0, activo=True).first()
            if plan:
                _agregar_plan(cotizacion, plan)
        elif accion in ("ia_regenerar", "ia_acortar", "ia_formal") and es_borrador:
            _accion_ia_cotizacion(request, cotizacion, accion)
        elif accion == "enviar" and es_borrador:
            if not cotizacion.items.exists():
                messages.error(request, "Agrega al menos un servicio antes de marcarla como enviada.")
            else:
                cotizacion.estado = Cotizacion.Estado.ENVIADA
                cotizacion.enviada_en = timezone.now()
                cotizacion.save(update_fields=["estado", "enviada_en", "actualizado_en"])
                # Solo avanza el embudo: un prospecto en etapa posterior (o perdido) no retrocede.
                if prospecto.etapa in (Prospecto.Etapa.NUEVO, Prospecto.Etapa.CONTACTADO, Prospecto.Etapa.REUNION):
                    _mover_etapa(prospecto, Prospecto.Etapa.COTIZACION_ENVIADA, request.user)
                _registrar(prospecto, request.user, f"Cotización #{cotizacion.numero} enviada", Interaccion.Tipo.CORREO)
                messages.success(
                    request,
                    "Cotización marcada como enviada. El correo automático se activa al configurar EMAIL_API_KEY; "
                    "mientras, compártela desde «Vista para imprimir / PDF».",
                )
        elif accion in ("aceptada", "rechazada") and cotizacion.estado == Cotizacion.Estado.ENVIADA:
            cotizacion.estado = accion
            cotizacion.respondida_en = timezone.now()
            cotizacion.save(update_fields=["estado", "respondida_en", "actualizado_en"])
            _registrar(prospecto, request.user, f"Cotización #{cotizacion.numero} {cotizacion.get_estado_display().lower()}")
            if accion == "aceptada":
                _mover_etapa(prospecto, Prospecto.Etapa.GANADO, request.user)
            messages.success(request, f"Cotización marcada como {cotizacion.get_estado_display().lower()}.")
        elif accion == "volver_borrador" and cotizacion.estado == Cotizacion.Estado.ENVIADA:
            cotizacion.estado = Cotizacion.Estado.BORRADOR
            cotizacion.enviada_en = None
            cotizacion.save(update_fields=["estado", "enviada_en", "actualizado_en"])
            messages.info(request, "La cotización volvió a borrador para editarla.")
        return redirect("crm:cotizacion_editar", pk=cotizacion.pk)

    items = list(cotizacion.items.select_related("plan", "servicio"))
    en_items_servicios = {i.servicio_id for i in items if i.servicio_id}
    en_items_planes = {i.plan_id for i in items if i.plan_id}
    totales = cotizacion.totales()
    checklist = [
        {"texto": "Prospecto con correo de contacto", "hecho": bool(prospecto.correo)},
        {"texto": "Al menos un servicio o plan", "hecho": bool(items)},
        {"texto": "Diagnóstico escrito", "hecho": bool(cotizacion.diagnostico.strip())},
        {"texto": "Diagnóstico IA revisado por el equipo", "hecho": bool(prospecto.diagnostico_revisado_en)},
        {"texto": "Validez y fecha de inicio definidas", "hecho": bool(cotizacion.valida_hasta and cotizacion.inicio_estimado)},
    ]
    context = contexto_panel(
        request,
        "cotizaciones",
        cotizacion=cotizacion,
        prospecto=prospecto,
        items=items,
        totales=totales,
        editable=cotizacion.estado == Cotizacion.Estado.BORRADOR,
        planes_disponibles=Plan.objects.filter(activo=True).exclude(pk__in=en_items_planes),
        servicios_disponibles=Servicio.objects.filter(activo=True).exclude(pk__in=en_items_servicios),
        formas_pago=Cotizacion.FormaPago.choices,
        descuentos=[(0, "Sin descuento"), (5, "5%"), (10, "10%"), (15, "15%")],
        checklist=checklist,
        ia_configurada=bool(settings.AI_API_KEY),
        maximo_diagnostico=4000,
    )
    return render(request, "crm/cotizacion_editar.html", context)


def _accion_ia_cotizacion(request, cotizacion, accion):
    try:
        if accion == "ia_regenerar":
            cotizacion.diagnostico = generar_diagnostico_cotizacion(cotizacion.prospecto, request.user)
            mensaje = "Diagnóstico regenerado con IA. Revísalo antes de enviar."
        else:
            instruccion = "Acórtalo a la mitad manteniendo lo esencial." if accion == "ia_acortar" else "Reescríbelo con un tono más formal, tratando de usted."
            cotizacion.diagnostico = reescribir_texto(cotizacion.diagnostico, instruccion, request.user, cotizacion.prospecto)
            mensaje = "Diagnóstico reescrito con IA. Revísalo antes de enviar."
        cotizacion.save(update_fields=["diagnostico", "actualizado_en"])
        messages.success(request, mensaje)
    except IANoConfigurada:
        messages.error(request, "La IA no está configurada: falta AI_API_KEY en el archivo .env.")
    except ErrorIA as e:
        messages.error(request, f"No se pudo usar la IA. {e}")


@solo_equipo
def cotizacion_imprimir(request, pk):
    cotizacion = get_object_or_404(Cotizacion.objects.select_related("prospecto"), pk=pk)
    return render(request, "crm/cotizacion_imprimir.html", {
        "cotizacion": cotizacion,
        "items": cotizacion.items.all(),
        "totales": cotizacion.totales(),
    })


# ── Clientes ──────────────────────────────────────────────────────────────────

@solo_equipo
def clientes(request):
    lista = Cliente.objects.select_related("prospecto").order_by("-creado_en")
    return render(request, "crm/clientes.html", contexto_panel(request, "clientes", clientes=lista))


# ── Usuarios (CU-08, Alcance 4.3 / 9.3) ────────────────────────────────────────

@requiere_administradora
def usuarios(request):
    lista = get_user_model().objects.select_related("cliente").order_by("username")
    rol_activo = request.GET.get("rol", "")
    if rol_activo in Rol.values:
        lista = lista.filter(rol=rol_activo)

    busqueda = request.GET.get("q", "").strip()
    if busqueda:
        lista = lista.filter(
            Q(username__icontains=busqueda)
            | Q(first_name__icontains=busqueda)
            | Q(last_name__icontains=busqueda)
            | Q(email__icontains=busqueda)
        )

    con_2fa = set(
        Authenticator.objects.filter(user__in=lista, type=Authenticator.Type.TOTP).values_list("user_id", flat=True)
    )

    return render(
        request,
        "crm/usuarios.html",
        contexto_panel(
            request, "usuarios",
            usuarios=lista, roles=Rol.choices, rol_activo=rol_activo, busqueda=busqueda,
            con_2fa=con_2fa,
        ),
    )


@requiere_administradora
def usuario_nuevo(request):
    if request.method == "POST":
        form = UsuarioForm(request.POST, es_nuevo=True)
        if form.is_valid():
            usuario = form.save()
            RegistroAuditoria.registrar(
                usuario=request.user,
                accion=RegistroAuditoria.Accion.CREAR,
                entidad="usuario",
                entidad_id=usuario.pk,
                detalle=f"{usuario.username} · {usuario.get_rol_display() or 'sin rol'}",
            )
            messages.success(request, f"Usuario «{usuario.username}» creado.")
            return redirect("crm:usuarios")
    else:
        form = UsuarioForm(es_nuevo=True)
    return render(
        request,
        "crm/usuario_form.html",
        contexto_panel(request, "usuarios", form=form, es_nuevo=True),
    )


@requiere_administradora
def usuario_editar(request, pk):
    usuario_obj = get_object_or_404(get_user_model(), pk=pk)
    if request.method == "POST":
        form = UsuarioForm(request.POST, instance=usuario_obj)
        if form.is_valid():
            form.save()
            RegistroAuditoria.registrar(
                usuario=request.user,
                accion=RegistroAuditoria.Accion.EDITAR,
                entidad="usuario",
                entidad_id=usuario_obj.pk,
                detalle=f"{usuario_obj.username} · {usuario_obj.get_rol_display() or 'sin rol'}",
            )
            messages.success(request, f"Usuario «{usuario_obj.username}» actualizado.")
            return redirect("crm:usuarios")
    else:
        form = UsuarioForm(instance=usuario_obj)
    return render(
        request,
        "crm/usuario_form.html",
        contexto_panel(request, "usuarios", form=form, usuario_editado=usuario_obj),
    )


@requiere_administradora
@require_POST
def usuario_alternar_activo(request, pk):
    usuario_obj = get_object_or_404(get_user_model(), pk=pk)
    if usuario_obj.pk == request.user.pk:
        messages.error(request, "No puedes desactivar tu propia cuenta.")
        return _volver(request, "crm:usuarios")

    usuario_obj.is_active = not usuario_obj.is_active
    usuario_obj.save(update_fields=["is_active"])
    RegistroAuditoria.registrar(
        usuario=request.user,
        accion=RegistroAuditoria.Accion.EDITAR,
        entidad="usuario",
        entidad_id=usuario_obj.pk,
        detalle=f"{usuario_obj.username} · {'activado' if usuario_obj.is_active else 'desactivado'}",
    )
    messages.success(request, f"Usuario «{usuario_obj.username}» {'activado' if usuario_obj.is_active else 'desactivado'}.")
    return _volver(request, "crm:usuarios")


@requiere_administradora
@require_POST
def usuario_restablecer_2fa(request, pk):
    usuario_obj = get_object_or_404(get_user_model(), pk=pk)
    autenticadores = Authenticator.objects.filter(user=usuario_obj)
    if not autenticadores.exists():
        messages.info(request, f"«{usuario_obj.username}» no tiene 2FA activado.")
        return _volver(request, "crm:usuarios")

    autenticadores.delete()
    RegistroAuditoria.registrar(
        usuario=request.user,
        accion=RegistroAuditoria.Accion.EDITAR,
        entidad="usuario",
        entidad_id=usuario_obj.pk,
        detalle=f"{usuario_obj.username} · 2FA restablecido (admin)",
    )
    messages.success(
        request,
        f"2FA de «{usuario_obj.username}» restablecido. Podrá iniciar sesión sin código "
        "y configurar la app autenticadora nuevamente desde su panel de Seguridad.",
    )
    return _volver(request, "crm:usuarios")


@requiere_administradora
def usuario_eliminar(request, pk):
    usuario_obj = get_user_model().objects.filter(pk=pk).first()
    if usuario_obj is None:
        # Ya fue eliminado (doble clic, otra pestaña, etc.): no es un error, solo avisamos.
        messages.info(request, "Ese usuario ya había sido eliminado.")
        return redirect("crm:usuarios")

    if usuario_obj.pk == request.user.pk:
        messages.error(request, "No puedes eliminar tu propia cuenta.")
        return redirect("crm:usuarios")

    if request.method == "POST":
        nombre, rol_mostrado = usuario_obj.username, usuario_obj.get_rol_display() or "sin rol"
        usuario_obj.delete()
        RegistroAuditoria.registrar(
            usuario=request.user,
            accion=RegistroAuditoria.Accion.ELIMINAR,
            entidad="usuario",
            entidad_id=pk,
            detalle=f"{nombre} · {rol_mostrado}",
        )
        messages.success(request, f"Usuario «{nombre}» eliminado.")
        return redirect("crm:usuarios")

    return render(
        request,
        "crm/usuario_confirmar_eliminar.html",
        contexto_panel(request, "usuarios", usuario_a_eliminar=usuario_obj),
    )


# ── Registro de auditoría (solo lectura) ────────────────────────────────────

@requiere_administradora
def auditoria(request):
    registros = RegistroAuditoria.objects.select_related("usuario").order_by("-creado_en")

    accion_activa = request.GET.get("accion", "")
    if accion_activa in RegistroAuditoria.Accion.values:
        registros = registros.filter(accion=accion_activa)

    busqueda = request.GET.get("q", "").strip()
    if busqueda:
        registros = registros.filter(
            Q(detalle__icontains=busqueda)
            | Q(entidad__icontains=busqueda)
            | Q(usuario__username__icontains=busqueda)
        )

    # Se muestran los últimos 300 movimientos; es un registro de solo lectura, no necesita paginación por ahora.
    registros = registros[:300]

    return render(
        request,
        "crm/auditoria.html",
        contexto_panel(
            request, "auditoria",
            registros=registros, acciones=RegistroAuditoria.Accion.choices,
            accion_activa=accion_activa, busqueda=busqueda,
        ),
    )
