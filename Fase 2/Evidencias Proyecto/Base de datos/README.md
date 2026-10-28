# Evidencias Proyecto · Base de datos

Documentación de la base de datos de la plataforma (PostgreSQL en Supabase).

- **`DDL-Plataforma-Cosmopolitan.sql`**: DDL del esquema `public` (33 tablas, con claves, índices y restricciones). Solo estructura, sin datos ni credenciales. Se generó a partir de las migraciones de Django, que son las mismas que se aplican en Supabase con `python manage.py migrate`.
- **`Anexo-Modelo-de-Datos-Cosmopolitan.docx`**: modelo de datos (diagrama E-R y diccionario de datos).
- Las migraciones están en `plataforma/apps/*/migrations/` (también dentro del zip de `Aplicación/`).
