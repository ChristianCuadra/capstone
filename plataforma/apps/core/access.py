"""Qué clientes puede ver cada usuario (PC-AUT-04 y PC-AUT-05, RNF-02).

Una sola regla, usada por el middleware, las vistas y el admin:
- Administradora, superusuario y personal sin rol asignado: todos los clientes.
- Colaboradora: solo los clientes que tiene asignados.
- Cliente aprobador / lector: solo su propia empresa.
- Cualquier otro usuario (o una sesión sin iniciar): ninguno.
"""

from django.http import Http404

from apps.accounts.models import Rol


def ids_permitidos(user):
    """None si el usuario no tiene restricción; si no, el conjunto de ids de cliente que sí puede ver."""
    if not getattr(user, "is_authenticated", False):
        return frozenset()
    if user.is_superuser or user.rol == Rol.ADMINISTRADORA:
        return None
    if user.rol == Rol.COLABORADORA:
        return frozenset(user.clientes_asignados.values_list("pk", flat=True))
    if user.es_cliente:
        return frozenset([user.cliente_id]) if user.cliente_id else frozenset()
    if user.is_staff and not user.rol:
        return None
    return frozenset()


def puede_aprobar(user):
    """Quién puede aprobar y enviar una cotización: la administradora (PC-COT-02).

    Se mantiene el acceso del personal sin rol asignado, igual que en ids_permitidos, hasta que
    todas las cuentas del equipo tengan su rol.
    """
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    return bool(user.is_superuser or user.rol == Rol.ADMINISTRADORA or (user.is_staff and not user.rol))


def clientes_visibles(user):
    """Queryset de clientes que el usuario puede ver."""
    from apps.clients.models import Cliente

    permitidos = ids_permitidos(user)
    if permitidos is None:
        return Cliente.objects.all()
    return Cliente.objects.filter(pk__in=permitidos)


def obtener_cliente_visible(user, pk):
    """El cliente pedido, o 404 si no existe o el usuario no tiene acceso (no revela cuál de las dos)."""
    from apps.clients.models import Cliente

    try:
        return clientes_visibles(user).get(pk=pk)
    except (Cliente.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404("Cliente no encontrado.") from exc
