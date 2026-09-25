"""Gestión comercial: prospectos captados desde el sitio y su historial (Documento de Alcance 5.3).

El formulario de cotización del sitio crea un Prospecto con todos los datos que usa la IA
para redactar el borrador del diagnóstico (Alcance 6.1): industria, tamaño, objetivos,
presupuesto, servicios requeridos y redes actuales.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

RUBROS = [
    "Gastronomía y cafeterías",
    "Retail y moda",
    "Salud y bienestar",
    "Belleza y estética",
    "Servicios profesionales",
    "Educación",
    "Inmobiliaria y construcción",
    "Turismo y hotelería",
    "Marca personal",
    "Otro",
]

REGIONES = [
    "Arica y Parinacota", "Tarapacá", "Antofagasta", "Atacama", "Coquimbo", "Valparaíso",
    "Metropolitana de Santiago", "O'Higgins", "Maule", "Ñuble", "Biobío", "La Araucanía",
    "Los Ríos", "Los Lagos", "Aysén", "Magallanes",
]

OBJETIVOS = [
    "Vender más online",
    "Aumentar seguidores",
    "Posicionar la marca",
    "Generar leads B2B",
    "Ordenar el contenido",
    "Mejorar el sitio web",
    "SEO local",
]

REDES = [
    ("instagram", "Instagram"),
    ("facebook", "Facebook"),
    ("tiktok", "TikTok"),
    ("linkedin", "LinkedIn"),
    ("sitio_web", "Sitio web"),
    ("ninguna", "Aún no tengo"),
]


class Prospecto(models.Model):
    class Etapa(models.TextChoices):
        NUEVO = "nuevo", "Nuevo"
        CONTACTADO = "contactado", "Contactado"
        REUNION = "reunion", "Reunión"
        COTIZACION_ENVIADA = "cotizacion_enviada", "Cotización enviada"
        GANADO = "ganado", "Ganado"
        PERDIDO = "perdido", "Perdido"

    class Tamano(models.TextChoices):
        SOLO = "solo", "Solo yo / emprendimiento"
        MICRO = "2_10", "2 a 10 personas"
        PEQUENA = "11_50", "11 a 50 personas"
        MEDIANA = "51_mas", "Más de 50 personas"

    class Presupuesto(models.TextChoices):
        MENOS_150 = "menos_150", "Menos de $150.000"
        DE_150_A_250 = "150_250", "$150.000 – $250.000"
        DE_250_A_350 = "250_350", "$250.000 – $350.000"
        MAS_350 = "mas_350", "Más de $350.000"

    class AgenciaActual(models.TextChoices):
        NO = "no", "No"
        SI = "si", "Sí"
        FREELANCE = "freelance", "Freelance"

    class ComoNosConocio(models.TextChoices):
        INSTAGRAM = "instagram", "Instagram"
        RECOMENDACION = "recomendacion", "Recomendación"
        GOOGLE = "google", "Google"
        LINKEDIN = "linkedin", "LinkedIn"
        OTRO = "otro", "Otro"

    class Canal(models.TextChoices):
        FORMULARIO_SITIO = "formulario_sitio", "Formulario del sitio"
        MANUAL = "manual", "Ingreso manual"

    # Contacto
    nombre = models.CharField(max_length=120)
    empresa = models.CharField(max_length=160)
    correo = models.EmailField()
    telefono = models.CharField("teléfono", max_length=30, blank=True)

    # Datos del negocio (entrada de la IA)
    rubro = models.CharField(max_length=60, choices=[(r, r) for r in RUBROS])
    region = models.CharField("región", max_length=60, choices=[(r, r) for r in REGIONES])
    tamano = models.CharField("tamaño", max_length=10, choices=Tamano.choices)
    agencia_actual = models.CharField("¿trabaja con agencia?", max_length=10, choices=AgenciaActual.choices)
    presupuesto = models.CharField("presupuesto mensual", max_length=10, choices=Presupuesto.choices)
    objetivos = models.JSONField(default=list, blank=True)
    redes_actuales = models.JSONField(default=list, blank=True)
    instagram = models.CharField("usuario de Instagram", max_length=60, blank=True)
    instagram_seguidores = models.PositiveIntegerField(
        "seguidores en Instagram", null=True, blank=True, help_text="Lo completa el equipo al revisar la cuenta."
    )
    sitio_web = models.URLField("sitio web", blank=True)
    servicios_requeridos = models.ManyToManyField("catalog.Servicio", blank=True, related_name="prospectos")
    situacion_actual = models.TextField("situación actual", blank=True)

    # Comercial
    plan_interes = models.ForeignKey(
        "catalog.Plan", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="plan de interés"
    )
    plan_sugerido = models.ForeignKey(
        "catalog.Plan", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="plan sugerido"
    )
    como_nos_conocio = models.CharField("¿cómo nos conoció?", max_length=20, choices=ComoNosConocio.choices, blank=True)
    canal = models.CharField(max_length=20, choices=Canal.choices, default=Canal.FORMULARIO_SITIO)
    etapa = models.CharField(max_length=20, choices=Etapa.choices, default=Etapa.NUEVO, db_index=True)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    acepta_privacidad = models.BooleanField("acepta la política de privacidad", default=False)
    cliente = models.OneToOneField(
        "clients.Cliente", null=True, blank=True, on_delete=models.SET_NULL, related_name="prospecto",
        help_text="Se completa al convertir el prospecto en cliente.",
    )

    # Borrador de diagnóstico generado por IA: siempre requiere revisión humana antes de usarse.
    diagnostico_ia = models.TextField("diagnóstico (borrador IA)", blank=True)
    diagnostico_generado_en = models.DateTimeField(null=True, blank=True)
    diagnostico_revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    diagnostico_revisado_en = models.DateTimeField(null=True, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "prospectos"
        verbose_name = "prospecto"
        verbose_name_plural = "prospectos"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.empresa} ({self.nombre})"

    @property
    def plan_referencia(self):
        """Plan para estimar el valor de la oportunidad: el sugerido o, si no hay, el de interés."""
        return self.plan_sugerido or self.plan_interes

    @property
    def valor_estimado(self):
        plan = self.plan_referencia
        return plan.precio_mensual if plan else None

    @property
    def dias_sin_movimiento(self):
        return (timezone.now() - self.actualizado_en).days

    def nombres_redes(self):
        nombres = dict(REDES)
        return [nombres.get(r, r) for r in self.redes_actuales]


class Tarea(models.Model):
    titulo = models.CharField("título", max_length=160)
    fecha = models.DateField("fecha límite", null=True, blank=True)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="tareas")
    prospecto = models.ForeignKey(Prospecto, null=True, blank=True, on_delete=models.CASCADE, related_name="tareas")
    completada = models.BooleanField(default=False)
    completada_en = models.DateTimeField(null=True, blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tareas"
        verbose_name = "tarea"
        verbose_name_plural = "tareas"
        ordering = ["completada", "fecha", "creado_en"]

    def __str__(self):
        return self.titulo


class Cotizacion(models.Model):
    """Propuesta comercial a un prospecto (Alcance 5.3, RF-04 y RF-05). Los precios se copian del catálogo al agregarlos."""

    class Estado(models.TextChoices):
        BORRADOR = "borrador", "Borrador"
        ENVIADA = "enviada", "Enviada"
        ACEPTADA = "aceptada", "Aceptada"
        RECHAZADA = "rechazada", "Rechazada"

    class FormaPago(models.TextChoices):
        TRANSFERENCIA_MENSUAL = "transferencia_mensual", "Transferencia mensual"
        SEMESTRAL = "semestral", "Pago semestral anticipado"
        TARJETA = "tarjeta", "Tarjeta de crédito (recurrente)"

    IVA = 0.19  # TODO: confirmar con la agencia si los precios del catálogo son netos (+ IVA)

    numero = models.CharField("número", max_length=20, unique=True, editable=False)
    prospecto = models.ForeignKey(Prospecto, on_delete=models.CASCADE, related_name="cotizaciones")
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.BORRADOR, db_index=True)
    contacto = models.CharField(max_length=200, blank=True)
    valida_hasta = models.DateField("válida hasta", null=True, blank=True)
    forma_pago = models.CharField("forma de pago", max_length=30, choices=FormaPago.choices, default=FormaPago.TRANSFERENCIA_MENSUAL)
    descuento_pct = models.PositiveSmallIntegerField("descuento (%)", default=0)
    inicio_estimado = models.DateField("inicio estimado", null=True, blank=True)
    diagnostico = models.TextField("diagnóstico", blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    enviada_en = models.DateTimeField(null=True, blank=True)
    respondida_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cotizaciones"
        verbose_name = "cotización"
        verbose_name_plural = "cotizaciones"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"Cotización {self.numero}"

    def save(self, *args, **kwargs):
        if not self.numero:
            anio = timezone.localdate().year
            ultimo = Cotizacion.objects.filter(numero__startswith=f"{anio}-").order_by("-numero").values_list("numero", flat=True).first()
            correlativo = int(ultimo.split("-")[1]) + 1 if ultimo else 1
            self.numero = f"{anio}-{correlativo:03d}"
        super().save(*args, **kwargs)

    def totales(self):
        items = list(self.items.all())
        recurrentes = sum(i.subtotal for i in items if i.meses)
        puntuales = sum(i.subtotal for i in items if not i.meses)
        descuento = round(recurrentes * self.descuento_pct / 100)
        neto = recurrentes + puntuales - descuento
        iva = round(neto * self.IVA)
        return {
            "recurrentes": recurrentes,
            "puntuales": puntuales,
            "descuento": descuento,
            "neto": neto,
            "iva": iva,
            "total": neto + iva,
            # Valor mensual recurrente (sin descuento ni IVA): base de ticket e ingresos mensuales.
            "mensual": sum(i.cantidad * i.valor_unitario for i in items if i.meses),
        }


class CotizacionItem(models.Model):
    cotizacion = models.ForeignKey(Cotizacion, on_delete=models.CASCADE, related_name="items")
    plan = models.ForeignKey("catalog.Plan", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    servicio = models.ForeignKey("catalog.Servicio", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    descripcion = models.CharField("descripción", max_length=160)
    detalle = models.CharField(max_length=255, blank=True)
    cantidad = models.PositiveSmallIntegerField(default=1)
    valor_unitario = models.PositiveIntegerField("valor unitario (CLP)")
    meses = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Vacío = cobro único.")
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "cotizacion_items"
        verbose_name = "ítem de cotización"
        verbose_name_plural = "ítems de cotización"
        ordering = ["orden", "pk"]

    def __str__(self):
        return self.descripcion

    @property
    def subtotal(self):
        return self.cantidad * self.valor_unitario * (self.meses or 1)


class Interaccion(models.Model):
    class Tipo(models.TextChoices):
        CORREO = "correo", "Correo"
        LLAMADA = "llamada", "Llamada"
        REUNION = "reunion", "Reunión"
        NOTA = "nota", "Nota interna"
        SISTEMA = "sistema", "Sistema"

    prospecto = models.ForeignKey(Prospecto, on_delete=models.CASCADE, related_name="interacciones")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    titulo = models.CharField("título", max_length=160)
    descripcion = models.TextField("descripción", blank=True)
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    fecha = models.DateTimeField(default=timezone.now)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "interacciones"
        verbose_name = "interacción"
        verbose_name_plural = "interacciones"
        ordering = ["-fecha"]

    def __str__(self):
        return self.titulo
