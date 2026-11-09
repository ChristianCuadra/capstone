from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from apps.accounts.views import activar_cuenta, login_admin
from apps.website.sitemaps import NovedadesSitemap, SitioPublicoSitemap

# El admin de Django no tiene login propio: se entra por el de allauth (con 2FA, límite de intentos y auditoría).
# Antes /admin/login/ aceptaba solo usuario y contraseña, saltándose esas protecciones.
admin.site.login = login_admin

urlpatterns = [
    path("admin/", admin.site.urls),
    # activación de la cuenta del cliente invitado (antes de allauth para que no la tape).
    path("accounts/activar/<uidb64>/<token>/", activar_cuenta, name="cuenta_activar"),
    path("accounts/", include("allauth.urls")),
    path("notificaciones/", include("apps.notifications.urls")),
    path("panel/metricas/", include("apps.metrics.urls")),
    path("", include("apps.reports.urls")),
    path("panel/", include("apps.crm.urls")),
    
    # Rutas del Sprint 3 (content/portal) cargadas sin prefijo para que respondan /panel/... y /portal/...
    path("", include("apps.content.urls")),
    
    # sitemap.xml del sitio publico (paginas fijas y novedades publicadas).
    path("sitemap.xml", sitemap, {"sitemaps": {"sitio": SitioPublicoSitemap, "novedades": NovedadesSitemap}}, name="sitemap"),
    path("", include("apps.website.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)