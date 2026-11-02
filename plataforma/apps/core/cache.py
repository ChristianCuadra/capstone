"""Caché compartida en la base de datos, tolerante a que su tabla todavía no exista.

En Vercel cada instancia tiene su propia memoria: con la caché por defecto (LocMem) los límites de intentos
de inicio de sesión (allauth) y de los formularios públicos se reiniciaban y no se compartían. Con esta caché
viven en la base (Supabase) y valen para todas las instancias.

Las migraciones de producción se aplican a mano (README): si el código llega antes que la tabla, en vez de
botar el inicio de sesión se usa la memoria de la instancia, como antes, hasta que la tabla exista.
"""

from django.core.cache.backends.db import DatabaseCache
from django.core.cache.backends.locmem import LocMemCache
from django.db import connections, router


class CacheBaseDatosTolerante(DatabaseCache):
    _tabla_lista = None  # por proceso: None = sin revisar, True/False = resultado

    def __init__(self, table, params):
        super().__init__(table, params)
        self._respaldo = LocMemCache(f"respaldo-{table}", {})

    def _usar_respaldo(self):
        if CacheBaseDatosTolerante._tabla_lista is None:
            try:
                db = router.db_for_read(self.cache_model_class)
                CacheBaseDatosTolerante._tabla_lista = self._table in connections[db].introspection.table_names()
            except Exception:
                return True  # sin base disponible ahora: memoria, y se vuelve a revisar en la próxima llamada
        return not CacheBaseDatosTolerante._tabla_lista

    def get(self, *args, **kwargs):
        return (self._respaldo if self._usar_respaldo() else super()).get(*args, **kwargs)

    def get_many(self, *args, **kwargs):
        return (self._respaldo if self._usar_respaldo() else super()).get_many(*args, **kwargs)

    def set(self, *args, **kwargs):
        return (self._respaldo if self._usar_respaldo() else super()).set(*args, **kwargs)

    def add(self, *args, **kwargs):
        return (self._respaldo if self._usar_respaldo() else super()).add(*args, **kwargs)

    def touch(self, *args, **kwargs):
        return (self._respaldo if self._usar_respaldo() else super()).touch(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return (self._respaldo if self._usar_respaldo() else super()).delete(*args, **kwargs)

    def delete_many(self, *args, **kwargs):
        return (self._respaldo if self._usar_respaldo() else super()).delete_many(*args, **kwargs)

    def has_key(self, *args, **kwargs):
        return (self._respaldo if self._usar_respaldo() else super()).has_key(*args, **kwargs)

    def clear(self):
        return (self._respaldo if self._usar_respaldo() else super()).clear()
