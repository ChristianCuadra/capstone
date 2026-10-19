"""Sitemap del sitio publico (PC-SEO-01): paginas fijas y novedades publicadas en el CMS (PC-SEO-01b)."""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class SitioPublicoSitemap(Sitemap):
    protocol = "https"
    changefreq = "weekly"

    def items(self):
        return [
            ("website:home", 1.0),
            ("website:planes", 0.8),
            ("website:cotizacion", 0.6),
            ("website:asesoria", 0.6),
        ]

    def location(self, item):
        nombre, _ = item
        return reverse(nombre)

    def priority(self, item):
        _, prioridad = item
        return prioridad


class NovedadesSitemap(Sitemap):
    """Entradas publicadas del CMS. Un borrador nunca aparece."""

    protocol = "https"
    changefreq = "monthly"
    priority = 0.5

    def items(self):
        from .models import Contenido

        return Contenido.objects.filter(estado=Contenido.Estado.PUBLICADO, seccion=Contenido.Seccion.NOVEDADES)

    def location(self, item):
        return reverse("website:novedad_detalle", args=[item.slug])

    def lastmod(self, item):
        return item.actualizado_en
