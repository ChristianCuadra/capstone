"""CMS del sitio corporativo (PC-WEB-02, Documento de Alcance 5.1).

La administradora crea y edita contenidos (novedades / recursos) sin tocar código.
Un contenido en borrador no es visible en el sitio público; solo lo publicado se muestra.
El texto se guarda sanitizado: se eliminan todas las etiquetas HTML al guardar (RNF-03, CP-008).
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.text import slugify


class Contenido(models.Model):
    class Seccion(models.TextChoices):
        NOVEDADES = "novedades", "Novedades"
        NOSOTRAS = "nosotras", "Nosotras"
        RECURSOS = "recursos", "Recursos"

    class Estado(models.TextChoices):
        BORRADOR = "borrador", "Borrador"
        PUBLICADO = "publicado", "Publicado"

    titulo = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    seccion = models.CharField(max_length=20, choices=Seccion.choices, default=Seccion.NOVEDADES)
    resumen = models.CharField(max_length=280, blank=True, help_text="Bajada corta para el listado. Opcional.")
    cuerpo = models.TextField(help_text="Texto de la entrada. Se guarda sin etiquetas HTML (sanitizado).")
    imagen = models.ImageField(upload_to="cms/%Y/%m/", blank=True, null=True)
    meta_titulo = models.CharField("meta título (SEO)", max_length=70, blank=True)
    meta_descripcion = models.CharField("meta descripción (SEO)", max_length=160, blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.BORRADOR)
    orden = models.PositiveSmallIntegerField(default=0)
    publicado_en = models.DateTimeField(null=True, blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="contenidos_cms"
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sitio_contenidos"
        verbose_name = "contenido del sitio"
        verbose_name_plural = "contenidos del sitio"
        ordering = ["orden", "-publicado_en", "-creado_en"]

    def __str__(self):
        return self.titulo

    @property
    def publicado(self):
        return self.estado == self.Estado.PUBLICADO

    def _slug_unico(self):
        base = slugify(self.titulo)[:200] or "contenido"
        slug, n = base, 2
        while Contenido.objects.exclude(pk=self.pk).filter(slug=slug).exists():
            slug = f"{base}-{n}"[:220]
            n += 1
        return slug

    def save(self, *args, **kwargs):
        # Sanitización: se eliminan todas las etiquetas HTML de los campos de texto (CP-008).
        self.titulo = strip_tags(self.titulo).strip()
        self.resumen = strip_tags(self.resumen).strip()
        self.cuerpo = strip_tags(self.cuerpo).strip()
        self.meta_titulo = strip_tags(self.meta_titulo).strip()
        self.meta_descripcion = strip_tags(self.meta_descripcion).strip()

        if not self.slug:
            self.slug = self._slug_unico()

        if self.estado == self.Estado.PUBLICADO and self.publicado_en is None:
            self.publicado_en = timezone.now()
        elif self.estado == self.Estado.BORRADOR:
            self.publicado_en = None

        super().save(*args, **kwargs)
