# Plataforma Cosmopolitan

Sitio corporativo, panel interno (CRM) y portal de clientes de la agencia. Django 5.1 + Tailwind (CDN) + Chart.js (CDN).

## Levantar en local

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env          # completar SECRET_KEY como mínimo
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Sin `DATABASE_URL` en `.env` se usa SQLite local; sin `AWS_STORAGE_BUCKET_NAME`, los archivos subidos quedan en `media/`.

## Rutas

| URL | Qué es |
|---|---|
| `/`, `/planes/`, `/cotizacion/` | Sitio corporativo (`apps/website`) |
| `/panel/` | Panel interno: dashboard, `prospectos/<slug>/`, `cotizaciones/nueva/` (`apps/crm`) |
| `/portal/` | Portal del cliente: `calendario/`, `aprobaciones/`, `metricas/` (`apps/content`) |
| `/accounts/` | Login (django-allauth) |
| `/admin/` | Admin de Django |

## Flujo comercial (funcional)

1. Un visitante completa `/cotizacion/` → se crea un **prospecto** (tabla `prospectos`) con plan sugerido por reglas.
2. En `/panel/prospectos/<id>/` el equipo lo gestiona: etapa, responsable, interacciones, Instagram,
   **diagnóstico con IA** (requiere `AI_API_KEY` de Google Gemini en `.env`; el borrador siempre se revisa) y
   «Convertir en cliente».
3. «Crear cotización» arma un borrador con precios del catálogo; se edita, se imprime/guarda como PDF desde el navegador
   y se marca enviada → aceptada/rechazada. Los KPIs del dashboard salen de estas cotizaciones.

El panel exige usuario del equipo (`is_staff`) y el portal, usuario con sesión. Sin datos, todo se muestra vacío.

## Estado actual

- **Catálogo de planes y servicios** (`apps/catalog`): en la base y editable en `/admin/` (Planes, Tipos de entregable, Servicios).
  La migración `catalog.0002_catalogo_inicial` carga los 4 planes y 7 servicios vigentes. El sitio (`/planes/` y servicios del inicio) lee de ahí.
- El resto de las vistas devuelve datos hardcodeados con la forma que tendrán las consultas.
  Cada dato pendiente está marcado con `TODO: Supabase - <tabla>` en `views.py` y en los templates.

Para entrar al admin, crear una cuenta: `.\.venv\Scripts\python.exe manage.py createsuperuser`

## Tests

```powershell
.\.venv\Scripts\python.exe manage.py test apps
```

`manage.py test` usa `config/settings/test.py` (SQLite en memoria): nunca crea bases en Supabase.

## Notas

- WeasyPrint (PDFs) necesita GTK/Pango instalado en el sistema. En Windows: instalar MSYS2 y `pacman -S mingw-w64-x86_64-pango`
  (ver https://doc.courtbouillon.org/weasyprint/stable/first_steps.html). Solo es necesario al implementar los PDFs.
- `config/settings/dev.py` es el único settings por ahora; falta un `prod.py` (HTTPS, DEBUG=False) antes de desplegar.
