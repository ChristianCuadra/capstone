from django.urls import path

from . import views

app_name = "metrics"

urlpatterns = [
    path("", views.panel_metricas, name="panel"),
    path("importar/", views.importar_archivo, name="importar"),
    path("plantilla/", views.descargar_plantilla, name="plantilla"),
]
