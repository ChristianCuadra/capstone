from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "content"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="content:calendario"), name="inicio"),
    path("calendario/", views.calendario, name="calendario"),
    path("aprobaciones/", views.aprobacion, name="aprobacion"),
    path("metricas/", views.metricas, name="metricas"),
]
