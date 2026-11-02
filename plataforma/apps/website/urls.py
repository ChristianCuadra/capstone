from django.urls import path

from . import views

app_name = "website"

urlpatterns = [
    path("", views.home, name="home"),
    path("planes/", views.planes, name="planes"),
    path("cotizacion/", views.cotizacion, name="cotizacion"),
    path("asesoria-gratuita/", views.asesoria, name="asesoria"),
    path("privacidad/", views.privacidad, name="privacidad"),
    path("novedades/", views.novedades, name="novedades"),
    path("novedades/<slug:slug>/", views.novedad_detalle, name="novedad_detalle"),
]
