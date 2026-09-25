"""Sitio corporativo público.

Planes y servicios ya vienen de la base (apps.catalog). El resto del contexto sigue hardcodeado:
cada bloque indica la tabla de Supabase desde la que se leerá.
Los montos van como enteros en CLP y se formatean en el template con el filtro `clp`.
"""

from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.catalog.models import Plan
from apps.catalog.services import comparativa_de_planes, planes_del_sitio, servicios_del_sitio
from apps.crm.models import Prospecto
from apps.crm.services import registrar_solicitud

from .forms import SolicitudCotizacionForm


def home(request):
    context = {
        # TODO: Supabase - tabla sitio_contenido (clave "hero")
        "hero": {
            "titulo": "Marketing digital que se nota en la caja, no solo en el",
            "titulo_cursiva": "feed",
            "titulo_final": ".",
            "subtitulo": "Somos dos socias y trabajamos con pocas marcas a la vez.",
            # {"etiqueta": "Caso …", "texto": "…"} cuando la agencia apruebe un caso real para destacar.
            "caso_destacado": None,
        },
        # Sin datos inventados: cifras, casos y testimonios se muestran solo cuando la agencia entregue los reales.
        # TODO: Supabase - tabla sitio_stats  ({"valor": "…", "etiqueta": "…"})
        "stats": [],
        # TODO: Supabase - sitio_contenido (clave "nosotras"). Equipo y metodología según el Documento de Alcance.
        "nosotras": {
            "intro": "Somos una agencia de marketing digital de dos socias. Trabajamos con emprendedores, pymes, "
            "marcas personales y empresas medianas, con un proceso ordenado y plazos que cumplimos.",
            "equipo": [
                {"nombre": "Pía Mercado", "cargo": "Directora de Estrategia y Marca", "iniciales": "PM"},
                {"nombre": "Valentina Frías", "cargo": "Directora de Contenido y Redes Sociales", "iniciales": "VF"},
            ],
            "metodologia": [
                {"titulo": "Diagnóstico y cotización", "texto": "Revisamos tu marca y te enviamos la propuesta en 3 días hábiles."},
                {"titulo": "Calendario editorial", "texto": "Planificamos el mes: qué se publica, dónde y con qué objetivo."},
                {"titulo": "Producción", "texto": "Grabamos y diseñamos. El material audiovisual se entrega en 5 días hábiles."},
                {"titulo": "Aprobación semanal", "texto": "Cada domingo apruebas desde tu portal las piezas de la semana."},
                {"titulo": "Reporte mensual", "texto": "Métricas del mes comparadas con el período anterior y próximos pasos."},
            ],
        },
        # Desde la base: catalog.Service (activos y visibles en el sitio)
        "servicios": servicios_del_sitio(),
        "plan_desde": min((p["precio_mensual"] for p in planes_del_sitio()), default=None),
        # TODO: Supabase - tabla casos (publicados, con autorización del cliente, límite 3)
        # {"cliente", "rubro", "metrica", "metrica_etiqueta", "detalle", "resumen"}
        "casos": [],
        # TODO: Supabase - tabla testimonios (publicados, con autorización)  {"cita", "autor", "cargo", "empresa"}
        "testimonios": [],
    }
    return render(request, "website/home.html", context)


def planes(request):
    # Desde la base: catalog.Plan + PlanDeliverable (activos y visibles en el sitio). Cobro solo mensual.
    planes_sitio = planes_del_sitio()
    context = {
        "planes": planes_sitio,
        "comparativa": comparativa_de_planes(planes_sitio),
        "servicios": servicios_del_sitio(),
    }
    return render(request, "website/planes.html", context)


LIMITE_SOLICITUDES_POR_HORA = 5


def _ip_cliente(request):
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return reenviada.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")


def cotizacion(request):
    """Formulario de cotización: guarda el prospecto (tabla prospectos) y le sugiere un plan.

    El diagnóstico con IA se genera después desde el panel y lo revisa el equipo antes de usarlo.
    """
    plan_interes = Plan.objects.filter(activo=True, slug=request.POST.get("plan") or request.GET.get("plan") or None).first()

    if request.method == "POST":
        form = SolicitudCotizacionForm(request.POST)
        clave_limite = f"cotizacion:{_ip_cliente(request)}"
        envios = cache.get(clave_limite, 0)
        if envios >= LIMITE_SOLICITUDES_POR_HORA:
            form.add_error(None, "Recibimos varias solicitudes desde tu conexión. Intenta en una hora o escríbenos por correo.")
        elif form.is_valid():
            cache.set(clave_limite, envios + 1, 60 * 60)
            if not form.es_spam():  # a un bot se le responde igual, pero no se guarda nada
                prospecto = registrar_solicitud(form, plan_interes)
                request.session["prospecto_enviado"] = prospecto.pk
            return redirect(reverse("website:cotizacion") + "?enviado=1")
    else:
        form = SolicitudCotizacionForm()

    enviado = request.GET.get("enviado") == "1"
    prospecto_enviado = None
    if enviado and request.session.get("prospecto_enviado"):
        prospecto_enviado = Prospecto.objects.select_related("plan_sugerido").filter(pk=request.session["prospecto_enviado"]).first()

    context = {
        "form": form,
        "enviado": enviado,
        "prospecto_enviado": prospecto_enviado,
        "plan_interes": plan_interes,
        # TODO: Supabase - tabla sitio_contenido (clave "cotizacion_beneficios")
        "beneficios": [
            {"titulo": "Cotización en 3 días hábiles", "texto": "Te escribe una de las socias, no un bot ni un ejecutivo de ventas."},
            {"titulo": "Cotización con diagnóstico", "texto": "Revisamos tus redes y tu objetivo antes de proponerte un plan."},
            {"titulo": "El plan que calza contigo", "texto": "Te sugerimos el plan según tu objetivo y presupuesto, o solo los servicios que necesitas."},
        ],
    }
    return render(request, "website/cotizacion.html", context)
