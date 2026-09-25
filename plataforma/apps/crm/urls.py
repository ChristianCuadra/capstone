from django.urls import path

from . import views

app_name = "crm"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("prospectos/", views.prospectos, name="prospectos"),
    path("prospectos/exportar/", views.prospectos_exportar, name="prospectos_exportar"),
    path("prospectos/<int:pk>/", views.prospecto_detalle, name="prospecto_detalle"),
    path("cotizaciones/", views.cotizaciones, name="cotizaciones"),
    path("cotizaciones/nueva/", views.cotizacion_nueva, name="cotizacion_nueva"),
    path("cotizaciones/<int:pk>/", views.cotizacion_editar, name="cotizacion_editar"),
    path("cotizaciones/<int:pk>/imprimir/", views.cotizacion_imprimir, name="cotizacion_imprimir"),
    path("tareas/nueva/", views.tarea_crear, name="tarea_crear"),
    path("tareas/<int:pk>/alternar/", views.tarea_alternar, name="tarea_alternar"),
    path("clientes/", views.clientes, name="clientes"),
]
