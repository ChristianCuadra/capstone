from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("panel/reportes/generar/", views.generar, name="generar"),
    path("panel/reportes/<int:pk>/", views.editar, name="editar"),
    path("panel/reportes/<int:pk>/pdf/", views.pdf_panel, name="pdf_panel"),
    path("portal/reportes/<int:pk>/pdf/", views.pdf_portal, name="pdf_portal"),
]
