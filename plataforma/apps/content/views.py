"""Portal del cliente: calendario editorial, aprobaciones y métricas.

Sin datos de ejemplo: las listas quedan vacías hasta crear el módulo de contenido
(tablas content_pieces, versiones, comentarios) y de métricas (metrics_data).
El cliente activo vendrá de request.client_id (apps.core.middleware.TenantMiddleware).
"""

import calendar
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

ESTADOS = [
    ("borrador", "Borrador"),
    ("en_revision", "En revisión"),
    ("aprobado", "Aprobado"),
    ("publicado", "Publicado"),
]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def contexto_portal(request, seccion, **context):
    """Datos comunes del layout del portal: usuario, cliente y badges."""
    u = request.user
    nombre = u.get_full_name() or u.email or u.username
    context["portal_usuario"] = {
        "nombre": nombre,
        "iniciales": "".join(p[0] for p in nombre.replace("@", " ").split()[:2]).upper(),
    }
    # TODO: cliente y plan del usuario (relación usuario ↔ cliente, Alcance 4.3)
    context["portal_cliente"] = None
    # TODO: count de content_pieces del cliente con estado = 'en_revision'
    context["portal_badges"] = {"aprobaciones": 0}
    context["seccion_portal"] = seccion
    return context


def _mes_desde_parametro(valor, hoy):
    try:
        anio, mes = (int(x) for x in valor.split("-"))
        return date(anio, mes, 1)
    except (ValueError, AttributeError):
        return hoy.replace(day=1)


@login_required
def calendario(request):
    hoy = timezone.localdate()
    primero = _mes_desde_parametro(request.GET.get("mes"), hoy)
    anterior = (primero - timedelta(days=1)).replace(day=1)
    siguiente = (primero + timedelta(days=32)).replace(day=1)

    piezas = []  # TODO: content_pieces del cliente en el mes
    por_dia = {}
    for pieza in piezas:
        por_dia.setdefault(pieza["fecha"], []).append(pieza)

    semanas = [
        [
            {"fecha": dia, "en_mes": dia.month == primero.month, "hoy": dia == hoy, "piezas": por_dia.get(dia, [])}
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
        total_piezas=len(piezas),
        en_revision=sum(1 for p in piezas if p["estado"] == "en_revision"),
        vista=vista,
        estados=ESTADOS,
        dias_semana=["L", "M", "M", "J", "V", "S", "D"],
        semanas=semanas,
        dias_con_piezas=[{"fecha": f, "hoy": f == hoy, "piezas": por_dia[f]} for f in sorted(por_dia)],
    )
    return render(request, "content/calendario.html", context)


@login_required
def aprobacion(request):
    # TODO: content_pieces en revisión + versiones + comentarios (Alcance 5.7). Aprobar es exclusivo del cliente aprobador.
    context = contexto_portal(request, "aprobaciones", pendientes=[], revisadas=[])
    return render(request, "content/aprobacion.html", context)


@login_required
def metricas(request):
    # TODO: metrics_data del cliente (importación por archivo o integración, Alcance 5.8) y reporte mensual (5.9).
    context = contexto_portal(request, "metricas", hay_datos=False)
    return render(request, "content/metricas.html", context)
