from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from apps.website.sitemaps import SitioPublicoSitemap

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("panel/", include("apps.crm.urls")),
    path("portal/", include("apps.content.urls")),
    # PC-SEO-01: sitemap.xml del sitio publico.
    path("sitemap.xml", sitemap, {"sitemaps": {"sitio": SitioPublicoSitemap}}, name="sitemap"),
    path("", include("apps.website.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
