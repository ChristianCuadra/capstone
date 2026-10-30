from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = "content"

urlpatterns = [
    # Rutas Portal Cliente 
    path("portal/", RedirectView.as_view(pattern_name="content:calendario"), name="inicio"),
    path("portal/calendario/", views.calendario, name="calendario"),
    path("portal/aprobaciones/", views.aprobacion, name="aprobacion"),
    path("portal/metricas/", views.metricas, name="metricas"),
    
    # Rutas Panel Interno / Colaboradoras 
    path("panel/calendario/", views.interna_calendario, name="interna_calendario"),
    path("panel/calendario/crear/", views.crear_pieza, name="crear_pieza"),
    path("panel/calendario/editar/<int:pieza_id>/", views.editar_pieza, name="editar_pieza"),
    path("panel/calendario/historial/<int:pieza_id>/", views.obtener_historial_pieza, name="obtener_historial_pieza"),
]