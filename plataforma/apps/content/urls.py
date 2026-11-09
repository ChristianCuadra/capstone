from django.urls import path
from django.views.generic import RedirectView

from apps.metrics.views import portal_metricas
from . import views, views_cumplimiento, views_ia, views_solicitudes

app_name = "content"

urlpatterns = [
    # Rutas Portal Cliente 
    path("portal/", RedirectView.as_view(pattern_name="content:calendario"), name="inicio"),
    path("portal/calendario/", views.calendario, name="calendario"),
    path("portal/aprobaciones/", views.aprobacion, name="aprobacion"),
    path("portal/metricas/", portal_metricas, name="metricas"),
    path("portal/solicitudes/", views_solicitudes.portal_solicitudes, name="solicitudes"),
    path("portal/solicitudes/<int:pk>/", views_solicitudes.portal_solicitud, name="solicitud"),
    path("portal/solicitudes/archivo/<int:pk>/", views_solicitudes.portal_archivo, name="solicitud_archivo"),
    
    # Rutas Panel Interno / Colaboradoras 
    path("panel/calendario/", views.interna_calendario, name="interna_calendario"),
    path("panel/calendario/crear/", views.crear_pieza, name="crear_pieza"),
    path("panel/calendario/editar/<int:pieza_id>/", views.editar_pieza, name="editar_pieza"),
    path("panel/calendario/historial/<int:pieza_id>/", views.obtener_historial_pieza, name="obtener_historial_pieza"),
    path("panel/calendario/copy-ia/", views_ia.copy_ia, name="copy_ia"),
    path("panel/cumplimiento/", views_cumplimiento.panel_cumplimiento, name="panel_cumplimiento"),
    path("panel/solicitudes/", views_solicitudes.panel_solicitudes, name="panel_solicitudes"),
    path("panel/solicitudes/<int:pk>/", views_solicitudes.panel_solicitud, name="panel_solicitud"),
    path("panel/solicitudes/archivo/<int:pk>/", views_solicitudes.panel_archivo, name="panel_solicitud_archivo"),
]