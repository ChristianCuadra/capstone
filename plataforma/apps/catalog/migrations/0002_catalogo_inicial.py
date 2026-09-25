"""Carga inicial del catálogo vigente de la agencia (planes mensuales y servicios sueltos).

Después de esta carga, el catálogo se mantiene desde el admin; no editar esta migración para cambiar precios.
"""

from django.db import migrations

# (slug, nombre, plural, con cuota, orden)
TIPOS = [
    ("historia", "Historia", "Historias", True, 1),
    ("carrusel", "Carrusel", "Carruseles", True, 2),
    ("reel", "Reel", "Reels", True, 3),
    ("flyer", "Flyer", "Flyers", True, 4),
    ("afiche", "Afiche", "Afiches", True, 5),
    ("branding", "Branding", "", False, 10),
    ("estrategia-digital", "Estrategia digital", "", False, 11),
    ("calendario-de-contenido", "Calendario de contenido", "", False, 12),
    ("copywriting", "Copywriting", "", False, 13),
    ("reporte-de-metricas", "Reporte de métricas", "", False, 14),
    ("gestion-de-publicidad", "Gestión de publicidad (Ads)", "", False, 15),
    ("servicios-tecnicos-digitales", "Servicios técnicos digitales", "", False, 16),
    ("marketing-de-influencers", "Marketing de influencers", "", False, 17),
    ("asesoria-estrategica", "Asesoría estratégica", "", False, 18),
    ("manual-de-marca", "Manual de marca", "", False, 19),
]

PRESENCIA = {"branding": None, "historia": 16, "carrusel": 4, "estrategia-digital": None}
POSICIONAMIENTO = {
    **PRESENCIA,
    "reel": 4,
    "calendario-de-contenido": None,
    "copywriting": None,
    "reporte-de-metricas": None,
    "gestion-de-publicidad": None,
}
CRECIMIENTO = {**POSICIONAMIENTO, "servicios-tecnicos-digitales": None, "marketing-de-influencers": None}
EXPANSION = {**CRECIMIENTO, "asesoria-estrategica": None}

# (slug, nombre, descripción, precio mensual, precio primer mes, entregables)
PLANES = [
    ("presencia", "Presencia", "Branding, 20 piezas al mes (16 historias y 4 carruseles) y estrategia digital.", 150000, None, PRESENCIA),
    ("posicionamiento", "Posicionamiento", "Todo Presencia, más 4 reels, calendario de contenido, copywriting, métricas y Ads.", 200000, None, POSICIONAMIENTO),
    ("crecimiento", "Crecimiento", "Todo Posicionamiento, más servicios técnicos digitales y marketing de influencers.", 300000, None, CRECIMIENTO),
    ("expansion", "Expansión", "Todo Crecimiento, más asesoría estratégica.", 350000, 400000, EXPANSION),
]

# (slug, nombre, precio, modalidad de cobro)
SERVICIOS = [
    ("asesorias-y-consultorias", "Asesorías y consultorías", 35000, "hora"),
    ("branding-rebranding", "Branding / Rebranding", 70000, "unico"),
    ("servicios-tecnicos-digitales", "Servicios técnicos digitales", 60000, "unico"),
    ("marketing-de-influencers", "Marketing de influencers", 50000, "campana"),
    ("contenido-audiovisual", "Contenido audiovisual (4 reels)", 80000, "paquete"),
    ("diseno-grafico", "Diseño gráfico (20 piezas)", 150000, "paquete"),
    ("publicidad-ads", "Publicidad Ads", 50000, "mensual"),
]


def cargar(apps, schema_editor):
    TipoEntregable = apps.get_model("catalog", "TipoEntregable")
    Plan = apps.get_model("catalog", "Plan")
    PlanEntregable = apps.get_model("catalog", "PlanEntregable")
    Servicio = apps.get_model("catalog", "Servicio")

    tipos = {}
    for slug, nombre, plural, cuota, orden in TIPOS:
        tipos[slug] = TipoEntregable.objects.create(slug=slug, nombre=nombre, nombre_plural=plural, tiene_cuota=cuota, orden=orden)

    for orden, (slug, nombre, descripcion, mensual, primer_mes, entregables) in enumerate(PLANES, start=1):
        plan = Plan.objects.create(
            slug=slug, nombre=nombre, descripcion=descripcion, precio_mensual=mensual, precio_primer_mes=primer_mes, orden=orden
        )
        PlanEntregable.objects.bulk_create(
            PlanEntregable(plan=plan, tipo_entregable=tipos[t], cantidad_mensual=cantidad) for t, cantidad in entregables.items()
        )

    for orden, (slug, nombre, precio, modalidad) in enumerate(SERVICIOS, start=1):
        Servicio.objects.create(slug=slug, nombre=nombre, precio=precio, modalidad_cobro=modalidad, orden=orden)


def descargar(apps, schema_editor):
    apps.get_model("catalog", "Plan").objects.filter(slug__in=[p[0] for p in PLANES]).delete()
    apps.get_model("catalog", "Servicio").objects.filter(slug__in=[s[0] for s in SERVICIOS]).delete()
    apps.get_model("catalog", "TipoEntregable").objects.filter(slug__in=[t[0] for t in TIPOS]).delete()


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]

    operations = [migrations.RunPython(cargar, descargar)]
