from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:pk>/", views.abrir, name="abrir"),
    path("<int:pk>/leida/", views.marcar_leida, name="marcar_leida"),
    path("leer-todas/", views.marcar_todas, name="marcar_todas"),
]
