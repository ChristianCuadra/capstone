"""Pantalla de cumplimiento del plan para la agencia (PC-CUM-01)."""

from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone

from apps.accounts.decorators import requiere_equipo
from apps.core.access import clientes_visibles

from .cumplimiento import cumplimiento_clientes


@requiere_equipo
def panel_cumplimiento(request):
    from apps.crm.views import contexto_panel

    from .views import MESES, _mes_desde_parametro

    hoy = timezone.localdate()
    primero = _mes_desde_parametro(request.GET.get("mes"), hoy)
    anterior = (primero - timedelta(days=1)).replace(day=1)
    siguiente = (primero + timedelta(days=32)).replace(day=1)
    clientes = clientes_visibles(request.user).filter(activo=True)
    datos = cumplimiento_clientes(clientes, primero, hoy)
    return render(request, "content/panel_cumplimiento.html", contexto_panel(
        request, "cumplimiento",
        datos=datos,
        en_riesgo=sum(1 for d in datos if d["en_riesgo"]),
        mes_nombre=MESES[primero.month - 1], anio=primero.year,
        mes_anterior=f"{anterior.year}-{anterior.month:02d}",
        mes_siguiente=f"{siguiente.year}-{siguiente.month:02d}",
        es_mes_actual=(primero.year, primero.month) == (hoy.year, hoy.month),
    ))
