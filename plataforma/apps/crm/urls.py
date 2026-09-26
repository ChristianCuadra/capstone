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
    path("usuarios/", views.usuarios, name="usuarios"),
    path("usuarios/nuevo/", views.usuario_nuevo, name="usuario_nuevo"),
    path("usuarios/<int:pk>/", views.usuario_editar, name="usuario_editar"),
    path("usuarios/<int:pk>/alternar/", views.usuario_alternar_activo, name="usuario_alternar_activo"),
    path("usuarios/<int:pk>/restablecer-2fa/", views.usuario_restablecer_2fa, name="usuario_restablecer_2fa"),
    path("usuarios/<int:pk>/eliminar/", views.usuario_eliminar, name="usuario_eliminar"),
    path("auditoria/", views.auditoria, name="auditoria"),
]
