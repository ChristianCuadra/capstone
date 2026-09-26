"""Sitemap del sitio publico (PC-SEO-01). Solo las paginas estaticas del sitio corporativo."""

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
        ]

    def location(self, item):
        nombre, _ = item
        return reverse(nombre)

    def priority(self, item):
        _, prioridad = item
        return prioridad
