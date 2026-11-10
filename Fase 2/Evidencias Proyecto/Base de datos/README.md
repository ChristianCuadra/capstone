# Evidencias Proyecto · Base de datos

Documentación de la base de datos de la plataforma (PostgreSQL en Supabase).

- **`DDL-Plataforma-Cosmopolitan.sql`**: DDL del esquema `public` (45 tablas: 30 del dominio y 15 de Django y sus librerías, con claves, índices, restricciones y RLS; actualizado al 9 de noviembre de 2026). Solo estructura, sin datos ni credenciales. Se generó a partir de las migraciones de Django, que son las mismas que se aplican en Supabase con `python manage.py migrate`.
- **`Anexo-Modelo-de-Datos-Cosmopolitan.docx`**: modelo de datos v2.0 (tres diagramas E-R y diccionario de las 30 tablas del dominio).
- Las migraciones están en `plataforma/apps/*/migrations/` (también dentro del zip de `Aplicación/`).
