# Plataforma Cosmopolitan

Sitio corporativo, panel interno (CRM) y portal de clientes de la agencia. Django 5.1 + Tailwind (CDN) + Chart.js (CDN).

## Levantar en local

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
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

## Despliegue en Vercel

En Vercel se importa el repositorio de GitHub con **Root Directory = `plataforma`**. `vercel.json` publica `config/wsgi.py`,
que en Vercel (variable `VERCEL=1`) usa `config/settings/prod.py`: DEBUG apagado, cookies seguras y estáticos servidos por
WhiteNoise sin `collectstatic`. Vercel instala solo `requirements.txt`; desarrollo y tests usan `requirements-dev.txt`.

Variables de entorno del proyecto en Vercel (Settings → Environment Variables):

| Variable | Valor |
|---|---|
| `SECRET_KEY` | Una clave larga y nueva (no la de desarrollo) |
| `DATABASE_URL` | La de Supabase con el pooler en modo transacción (puerto 6543) |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL`, `AWS_S3_REGION_NAME` | Supabase Storage (documentos y CMS) |
| `AI_API_KEY` | Clave de Gemini (opcional; sin ella la IA queda desactivada) |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | Solo si se usa un dominio propio (por defecto `.vercel.app`) |

No copiar `DEBUG` ni `ALLOWED_HOSTS=localhost` del `.env` local. Las migraciones se aplican desde un equipo local
(`manage.py migrate` con el `DATABASE_URL` de Supabase), no en Vercel. Mientras no haya proveedor de correo,
los correos quedan en los logs de Vercel.

## Notas

- WeasyPrint (PDFs) necesita GTK/Pango instalado en el sistema. En Windows: instalar MSYS2 y `pacman -S mingw-w64-x86_64-pango`
  (ver https://doc.courtbouillon.org/weasyprint/stable/first_steps.html). Solo es necesario al implementar los PDFs.
- `config/settings/prod.py` es el de producción (Vercel); `dev.py` el local y `test.py` el de los tests.
