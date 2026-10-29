from django.urls import path
from . import views

app_name = "content"

urlpatterns = [
    # Rutas Portal Cliente (PC-POR-01)
    path("portal/calendario/", views.calendario, name="calendario"),
    path("portal/aprobaciones/", views.aprobacion, name="aprobacion"),
    path("portal/metricas/", views.metricas, name="metricas"),
    
    # Rutas Panel Interno / Colaboradoras (PC-CAL-01, PC-CAL-02)
    path("panel/calendario/", views.interna_calendario, name="interna_calendario"),
    path("panel/calendario/crear/", views.crear_pieza, name="crear_pieza"),
]