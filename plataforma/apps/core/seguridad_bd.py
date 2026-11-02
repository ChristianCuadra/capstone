"""Medidas sobre la base que se aplican al final de cada `migrate` (también las tablas que se agreguen después).

1. Tabla de la caché compartida (settings.CACHES): `createcachetable` no hace nada si ya existe.
2. Row Level Security en Supabase: Supabase publica automáticamente las tablas del esquema `public` en su API
   REST (PostgREST). La plataforma no usa esa API, pero si alguien obtiene la clave pública del proyecto podría
   leer las tablas sin RLS. Se activa RLS sin políticas: la API no ve ninguna fila.
   Django no se ve afectado porque se conecta con el usuario dueño de las tablas, y en PostgreSQL el dueño no
   queda sujeto a RLS (salvo FORCE, que no se usa). Por eso solo se tocan tablas cuyo dueño es ese usuario.
"""

from django.core.management import call_command
from django.db import DEFAULT_DB_ALIAS, connections

SQL_TABLAS_SIN_RLS = """
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND NOT c.relrowsecurity
      AND pg_get_userbyid(c.relowner) = current_user
"""


def activar_rls(using=DEFAULT_DB_ALIAS):
    """Activa RLS en las tablas propias del esquema public. Devuelve los nombres de las tablas tocadas."""
    conexion = connections[using]
    if conexion.vendor != "postgresql":
        return []
    with conexion.cursor() as cursor:
        cursor.execute(SQL_TABLAS_SIN_RLS)
        tablas = [fila[0] for fila in cursor.fetchall()]
        for tabla in tablas:
            cursor.execute(f"ALTER TABLE {conexion.ops.quote_name(tabla)} ENABLE ROW LEVEL SECURITY")
    return tablas


def asegurar_base(sender, using=DEFAULT_DB_ALIAS, verbosity=1, **kwargs):
    call_command("createcachetable", database=using, verbosity=0)
    tablas = activar_rls(using)
    if tablas and verbosity:
        print(f"  RLS activado en {len(tablas)} tabla(s) de Supabase.")
