from django.urls import path

from . import views

app_name = "website"

urlpatterns = [
    path("", views.home, name="home"),
    path("planes/", views.planes, name="planes"),
    path("cotizacion/", views.cotizacion, name="cotizacion"),
]
