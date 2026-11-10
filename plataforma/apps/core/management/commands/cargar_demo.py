"""Carga datos de demostración en un cliente de prueba para mostrar el portal con contenido.

Uso:
    python manage.py cargar_demo                     # cliente del usuario cliente.prueba
    python manage.py cargar_demo --usuario correo@x  # otro usuario cliente
    python manage.py cargar_demo --borrar            # quita lo que cargó este comando

Todo lo que crea queda marcado para poder borrarlo después:
- piezas y solicitudes: llevan #CosmopolitanDemo en el texto;
- métricas: cuelgan de la importación «demo-metricas.csv»;
- reporte mensual: su texto empieza con «Reporte de demostración».
No envía correos: los avisos se crean solo dentro de la plataforma.
"""

import datetime as dt
import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Rol
from apps.catalog.models import Plan
from apps.clients.models import KPICliente, MedicionKPI
from apps.content.models import (
    ComentarioPieza,
    EstadoPieza,
    HistorialVersionPieza,
    MensajeSolicitud,
    PiezaContenido,
    RedSocial,
    Solicitud,
)
from apps.metrics.models import Fuente, ImportacionMetricas, MetricaDiaria
from apps.notifications.models import Notificacion
from apps.reports.models import ReporteMensual

MARCA = "#CosmopolitanDemo"
ARCHIVO_DEMO = "demo-metricas.csv"
INICIO_REPORTE = "Reporte de demostración"
ASUNTOS = ["Cambiar la foto de la campaña de diciembre", "Agregar el horario de atención en las historias"]

IDEAS = [
    "Lanzamiento de la colección de verano", "Detrás de escena del equipo", "Testimonio de una clienta",
    "Tips para elegir tu producto ideal", "Promoción de fin de mes", "Pregunta frecuente de la semana",
    "Nuestro proceso paso a paso", "Antes y después", "Día de la madre: idea de regalo", "Conoce a nuestro equipo",
    "Novedades de la temporada", "Encuesta: ¿qué quieres ver?", "Concurso para seguidores", "Recomendación del mes",
    "Frase de la semana", "Cómo usar nuestro producto", "Error común y cómo evitarlo", "Agenda tu hora",
]


def _primer_dia(fecha):
    return fecha.replace(day=1)


def _mes_anterior(primero):
    return (primero - dt.timedelta(days=1)).replace(day=1)


class Command(BaseCommand):
    help = "Carga datos de demostración (calendario, solicitudes, métricas, KPI y reporte) en un cliente de prueba."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", default="cliente.prueba", help="Usuario o correo de un usuario del cliente.")
        parser.add_argument("--borrar", action="store_true", help="Quita los datos de demostración de ese cliente.")

    def handle(self, *args, **opts):
        User = get_user_model()
        u = User.objects.filter(Q(username__iexact=opts["usuario"]) | Q(email__iexact=opts["usuario"])).first()
        if not u or not u.cliente_id:
            raise CommandError(f"No encontré un usuario de cliente «{opts['usuario']}».")
        cliente = u.cliente
        if opts["borrar"]:
            self._borrar(cliente)
            return
        agencia = (
            User.objects.filter(rol=Rol.ADMINISTRADORA, is_active=True).order_by("id").first()
            or User.objects.filter(is_superuser=True).order_by("id").first()
        )
        aprobador = (
            User.objects.filter(cliente=cliente, rol=Rol.CLIENTE_APROBADOR, is_active=True).order_by("id").first() or u
        )
        with transaction.atomic():
            self._cargar(cliente, agencia, aprobador)

    # ------------------------------------------------------------------ carga
    def _cargar(self, cliente, agencia, aprobador):
        rnd = random.Random(cliente.pk)
        hoy = timezone.localdate()
        este_mes = _primer_dia(hoy)
        mes_pasado = _mes_anterior(este_mes)

        if PiezaContenido.all_objects.filter(cliente=cliente, texto__contains=MARCA).exists():
            self.stdout.write(self.style.WARNING("Este cliente ya tiene datos de demostración. Usa --borrar antes de volver a cargar."))
            return

        if cliente.plan is None:
            plan = Plan.objects.filter(activo=True, entregables__tipo_entregable__tiene_cuota=True).distinct().order_by("orden").first()
            if plan:
                cliente.plan = plan
                if not cliente.fecha_inicio_contrato:
                    cliente.fecha_inicio_contrato = mes_pasado
                cliente.save(update_fields=["plan", "fecha_inicio_contrato"])
                self.stdout.write(f"El cliente no tenía plan: se le asignó «{plan.nombre}».")

        piezas = self._piezas(cliente, agencia, aprobador, rnd, mes_pasado, este_mes, hoy)
        solicitudes = self._solicitudes(cliente, agencia, aprobador)
        metricas = self._metricas(cliente, agencia, rnd, hoy)
        kpis = self._kpis(cliente, agencia, hoy)
        reporte = self._reporte(cliente, agencia, mes_pasado)
        Notificacion.objects.create(
            usuario=aprobador, titulo="Tienes piezas por revisar",
            mensaje="La agencia envió piezas del calendario para tu aprobación.",
        )
        Notificacion.objects.create(
            usuario=aprobador, titulo="La agencia respondió tu solicitud", mensaje=ASUNTOS[0],
        )
        self.stdout.write(self.style.SUCCESS(
            f"Listo para «{cliente}»: {piezas} piezas, {solicitudes} solicitudes, {metricas} días de métricas, "
            f"{kpis} KPI nuevos y {'1 reporte' if reporte else 'sin reporte nuevo'}."
        ))

    def _piezas(self, cliente, agencia, aprobador, rnd, mes_pasado, este_mes, hoy):
        tipos = []
        if cliente.plan:
            for pe in cliente.plan.entregables.select_related("tipo_entregable").filter(tipo_entregable__tiene_cuota=True):
                tipos.append((pe.tipo_entregable, min(pe.cantidad_mensual or 0, 8)))
        if not tipos:
            tipos = [(None, 6)]
        ideas = iter(IDEAS * 10)
        total = 0
        redes = [RedSocial.INSTAGRAM, RedSocial.INSTAGRAM, RedSocial.FACEBOOK]
        for primero, es_actual in ((mes_pasado, False), (este_mes, True)):
            dias_mes = ((primero + dt.timedelta(days=32)).replace(day=1) - primero).days
            for tipo, cantidad in tipos:
                for i in range(cantidad):
                    dia = min(dias_mes, 2 + round(i * (dias_mes - 3) / max(cantidad - 1, 1)))
                    fecha = primero.replace(day=dia)
                    if not es_actual or fecha < hoy - dt.timedelta(days=2):
                        estado = EstadoPieza.PUBLICADO if (i % 3) else EstadoPieza.APROBADO
                    elif fecha <= hoy + dt.timedelta(days=6):
                        estado = EstadoPieza.EN_REVISION
                    else:
                        estado = EstadoPieza.BORRADOR
                    titulo = next(ideas)
                    p = PiezaContenido.all_objects.create(
                        cliente=cliente, titulo=titulo,
                        texto=f"{titulo}. Te contamos todo en nuestras redes. {MARCA}",
                        red_social=redes[i % len(redes)], estado=estado,
                        fecha_programada=timezone.make_aware(dt.datetime.combine(fecha, dt.time(10 + (i % 8), 0))),
                        tipo_entregable=tipo, creado_por=agencia,
                    )
                    if estado in (EstadoPieza.APROBADO, EstadoPieza.PUBLICADO):
                        p.aprobado_por = aprobador
                        p.fecha_aprobacion = p.fecha_programada - dt.timedelta(days=2)
                        p.save(update_fields=["aprobado_por", "fecha_aprobacion"])
                    total += 1
        # Una pieza con cambios pedidos y su versión anterior, para mostrar el historial.
        p = PiezaContenido.all_objects.filter(cliente=cliente, texto__contains=MARCA, estado=EstadoPieza.EN_REVISION).first()
        if p:
            HistorialVersionPieza.objects.create(
                pieza=p, version=1, titulo=p.titulo, texto=p.texto.replace("Te contamos", "Mira"),
                estado_al_guardar=EstadoPieza.RECHAZADO, modificado_por=agencia,
            )
            ComentarioPieza.objects.create(
                pieza=p, usuario=aprobador, comentario="Usar el logo nuevo y cambiar el fondo a uno más claro.",
            )
            p.version = 2
            p.save(update_fields=["version"])
        return total

    def _solicitudes(self, cliente, agencia, aprobador):
        s1 = Solicitud.all_objects.create(cliente=cliente, asunto=ASUNTOS[0], estado=Solicitud.Estado.RESPONDIDA, creado_por=aprobador)
        MensajeSolicitud.objects.create(solicitud=s1, usuario=aprobador, texto=f"Queremos usar la foto de la tienda nueva en la campaña. {MARCA}")
        MensajeSolicitud.objects.create(solicitud=s1, usuario=agencia, texto="¡Listo! La cambiamos y queda en el calendario para su revisión.")
        s2 = Solicitud.all_objects.create(cliente=cliente, asunto=ASUNTOS[1], creado_por=aprobador)
        MensajeSolicitud.objects.create(solicitud=s2, usuario=aprobador, texto=f"Atendemos de lunes a sábado de 10:00 a 19:00. {MARCA}")
        return 2

    def _metricas(self, cliente, agencia, rnd, hoy):
        desde = _mes_anterior(_mes_anterior(_primer_dia(hoy)))
        hasta = hoy - dt.timedelta(days=1)
        imp = ImportacionMetricas.all_objects.create(
            cliente=cliente, fuente=Fuente.INSTAGRAM, nombre_archivo=ARCHIVO_DEMO, desde=desde, hasta=hasta, subido_por=agencia,
        )
        existentes = set(
            MetricaDiaria.all_objects.filter(cliente=cliente, fecha__range=(desde, hasta)).values_list("fecha", "fuente")
        )
        seguidores = 1200
        n = 0
        dia = desde
        nuevas = []
        while dia <= hasta:
            seguidores += rnd.randint(1, 7)
            if (dia, Fuente.INSTAGRAM) not in existentes:
                alcance = rnd.randint(900, 2600)
                nuevas.append(MetricaDiaria(
                    cliente=cliente, fecha=dia, fuente=Fuente.INSTAGRAM, alcance=alcance,
                    impresiones=int(alcance * rnd.uniform(1.3, 1.8)), interacciones=rnd.randint(40, 180),
                    seguidores=seguidores, clics=rnd.randint(5, 40), importacion=imp,
                ))
                n += 1
            if dia >= desde + dt.timedelta(days=30) and (dia, Fuente.META_ADS) not in existentes:
                alcance = rnd.randint(1500, 4000)
                nuevas.append(MetricaDiaria(
                    cliente=cliente, fecha=dia, fuente=Fuente.META_ADS, alcance=alcance,
                    impresiones=int(alcance * rnd.uniform(1.5, 2.2)), clics=rnd.randint(30, 120),
                    gasto=Decimal(rnd.randint(4000, 9000)), resultados=rnd.randint(2, 15), importacion=imp,
                ))
            dia += dt.timedelta(days=1)
        MetricaDiaria.all_objects.bulk_create(nuevas)
        imp.filas = len(nuevas)
        imp.save(update_fields=["filas"])
        return n

    def _kpis(self, cliente, agencia, hoy):
        creados = 0
        for indicador, inicial, meta, valores in (
            (KPICliente.Indicador.SEGUIDORES, 1200, 1600, [1290, 1385, 1430]),
            (KPICliente.Indicador.ALCANCE, 30000, 45000, [33500, 38200, 40100]),
        ):
            if KPICliente.all_objects.filter(cliente=cliente, indicador=indicador).exists():
                continue
            kpi = KPICliente.all_objects.create(cliente=cliente, indicador=indicador, valor_inicial=inicial, meta=meta)
            for k, valor in enumerate(valores):
                MedicionKPI.all_objects.create(
                    cliente=cliente, kpi=kpi, fecha=hoy - dt.timedelta(days=60 - 28 * k), valor=valor, registrado_por=agencia,
                )
            creados += 1
        return creados

    def _reporte(self, cliente, agencia, mes):
        if ReporteMensual.all_objects.filter(cliente=cliente, mes=mes).exists():
            return None
        texto = (
            f"{INICIO_REPORTE} (datos de ejemplo).\n"
            "1. Resumen del mes\n"
            "Se cumplió el plan contratado: todas las piezas del mes se publicaron después de su aprobación.\n"
            "2. Lo que mejor funcionó\n"
            "Los reels y los carruseles con testimonios tuvieron el mayor alcance y la mayor interacción.\n"
            "3. Recomendaciones para el próximo mes\n"
            "Mantener dos testimonios al mes y probar una campaña corta con un llamado a agendar hora."
        )
        return ReporteMensual.all_objects.create(
            cliente=cliente, mes=mes, contenido=texto, estado=ReporteMensual.Estado.APROBADO,
            creado_por=agencia, aprobado_por=agencia, fecha_aprobacion=timezone.now(),
        )

    # ------------------------------------------------------------------ borrado
    def _borrar(self, cliente):
        with transaction.atomic():
            p = PiezaContenido.all_objects.filter(cliente=cliente, texto__contains=MARCA).delete()[0]
            ids = MensajeSolicitud.objects.filter(solicitud__cliente=cliente, texto__contains=MARCA).values_list("solicitud_id", flat=True)
            s = Solicitud.all_objects.filter(pk__in=list(ids)).delete()[0]
            imps = ImportacionMetricas.all_objects.filter(cliente=cliente, nombre_archivo=ARCHIVO_DEMO)
            m = MetricaDiaria.all_objects.filter(importacion__in=imps).delete()[0]
            imps.delete()
            r = ReporteMensual.all_objects.filter(cliente=cliente, contenido__startswith=INICIO_REPORTE).delete()[0]
        self.stdout.write(self.style.SUCCESS(
            f"Datos de demostración quitados de «{cliente}» (registros borrados: piezas {p}, solicitudes {s}, métricas {m}, reportes {r}). "
            "Los KPI y avisos creados se mantienen; bórralos desde la ficha si no los quieres."
        ))
