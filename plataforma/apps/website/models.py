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


class MetadatosPagina(models.Model):
    """Título y descripción SEO de las páginas fijas del sitio, editables desde el CMS (PC-SEO-01b, CP-009).

    Si un campo queda vacío, la página usa el texto que trae por defecto (PC-SEO-01). Así nada cambia
    en el sitio hasta que la administradora lo defina.
    """

    class Pagina(models.TextChoices):
        # El valor es el nombre de la URL en apps.website.urls (website:<valor>).
        HOME = "home", "Inicio"
        PLANES = "planes", "Planes"
        COTIZACION = "cotizacion", "Solicitar cotización"
        ASESORIA = "asesoria", "Asesoría gratuita"
        NOVEDADES = "novedades", "Novedades (listado)"

    pagina = models.CharField("página", max_length=20, choices=Pagina.choices, unique=True)
    meta_titulo = models.CharField(
        "meta título (SEO)", max_length=70, blank=True, help_text="Se muestra en la pestaña y en Google. Al final se agrega el nombre de la agencia."
    )
    meta_descripcion = models.CharField(
        "meta descripción (SEO)", max_length=160, blank=True, help_text="Texto bajo el título en los resultados de búsqueda."
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sitio_metadatos_paginas"
        verbose_name = "metadatos SEO de página"
        verbose_name_plural = "metadatos SEO de páginas"
        ordering = ["pagina"]

    def __str__(self):
        return self.get_pagina_display()

    def save(self, *args, **kwargs):
        # Sanitización igual que el resto del CMS (RNF-03, CP-008).
        self.meta_titulo = strip_tags(self.meta_titulo).strip()
        self.meta_descripcion = strip_tags(self.meta_descripcion).strip()
        super().save(*args, **kwargs)


class ConfiguracionAgencia(models.Model):
    """Datos de contacto de la agencia que se muestran en el sitio, la cotización y los avisos por correo.

    Registro único (pk=1), editable por la administradora en Panel → Configuración. Los valores por defecto
    son los provisorios que tenía el sitio, así nada cambia hasta que la agencia entregue los reales.
    El correo es también el destino de los avisos de asesoría gratuita.
    """

    correo = models.EmailField("correo de contacto", default="hola@agenciacosmopolitan.cl")
    telefono = models.CharField("teléfono", max_length=30, default="+56 9 8765 4321", help_text="Como se muestra en el sitio, ej. +56 9 1234 5678.")
    whatsapp = models.CharField(
        "WhatsApp", max_length=15, default="56987654321", help_text="Solo números, con código de país y sin «+». Ej.: 56912345678."
    )
    ciudad = models.CharField(max_length=80, default="Santiago, Chile")
    instagram_usuario = models.CharField(
        "usuario de Instagram", max_length=30, blank=True, help_text="Sin @. Vacío = no se muestra en el sitio."
    )
    linkedin_nombre = models.CharField("nombre en LinkedIn", max_length=80, blank=True)
    linkedin_url = models.URLField("URL de LinkedIn", blank=True, help_text="Vacío = no se muestra en el sitio.")
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agencia_config"
        verbose_name = "configuración de la agencia"
        verbose_name_plural = "configuración de la agencia"

    def __str__(self):
        return "Configuración de la agencia"

    def save(self, *args, **kwargs):
        self.pk = 1  # registro único
        self.instagram_usuario = self.instagram_usuario.strip().lstrip("@")
        self.whatsapp = "".join(c for c in self.whatsapp if c.isdigit())
        super().save(*args, **kwargs)

    @classmethod
    def actual(cls):
        """La configuración guardada, o una con los valores por defecto (sin guardarla) si aún no existe."""
        return cls.objects.filter(pk=1).first() or cls(pk=1)
