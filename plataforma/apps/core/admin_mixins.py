from .models import RegistroAuditoria


class AuditoriaAdminMixin:
    """Mixin para ModelAdmin: deja un RegistroAuditoria por cada crear/editar/eliminar.

    Pensado para módulos que hoy se administran solo desde /admin/ (sin vista propia
    en el panel), como el catálogo de planes y servicios (Documento de Alcance 9.2).
    """

    auditoria_entidad = None  # nombre a mostrar en la bitácora; por defecto el verbose_name del modelo

    def _auditoria_entidad(self):
        return self.auditoria_entidad or str(self.model._meta.verbose_name)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        RegistroAuditoria.registrar(
            usuario=request.user,
            accion=RegistroAuditoria.Accion.EDITAR if change else RegistroAuditoria.Accion.CREAR,
            entidad=self._auditoria_entidad(),
            entidad_id=obj.pk,
            detalle=str(obj),
        )

    def delete_model(self, request, obj):
        entidad_id, detalle = obj.pk, str(obj)
        super().delete_model(request, obj)
        RegistroAuditoria.registrar(
            usuario=request.user,
            accion=RegistroAuditoria.Accion.ELIMINAR,
            entidad=self._auditoria_entidad(),
            entidad_id=entidad_id,
            detalle=detalle,
        )

    def delete_queryset(self, request, queryset):
        # Acción masiva "Eliminar seleccionados": se registra cada objeto antes de borrarlo.
        registros = [(obj.pk, str(obj)) for obj in queryset]
        super().delete_queryset(request, queryset)
        for entidad_id, detalle in registros:
            RegistroAuditoria.registrar(
                usuario=request.user,
                accion=RegistroAuditoria.Accion.ELIMINAR,
                entidad=self._auditoria_entidad(),
                entidad_id=entidad_id,
                detalle=detalle,
            )
