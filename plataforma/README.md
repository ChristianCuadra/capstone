# Plataforma Cosmopolitan

Sitio corporativo, panel interno (CRM) y portal de clientes de la agencia. Django 5.2 (LTS) + Supabase PostgreSQL + Tailwind (CDN) + Chart.js (CDN).

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
| `/`, `/planes/`, `/cotizacion/`, `/asesoria-gratuita/`, `/novedades/`, `/privacidad/` | Sitio corporativo (`apps/website`) |
| `/panel/` | Panel interno: dashboard, `prospectos/`, `cotizaciones/`, `clientes/`, `usuarios/`, `auditoria/`, `planes-servicios/`, `contenidos/`, `configuracion/` (`apps/crm`) |
| `/panel/calendario/`, `/panel/cumplimiento/`, `/panel/solicitudes/` | Calendario editorial, cumplimiento del plan y solicitudes (`apps/content`) |
| `/panel/metricas/`, `/panel/reportes/` | Carga de métricas por archivo y reportes mensuales (`apps/metrics`, `apps/reports`) |
| `/portal/` | Portal del cliente: `calendario/`, `aprobaciones/`, `metricas/`, `solicitudes/` (`apps/content`) |
| `/accounts/` | Inicio de sesión, activación de cuenta y 2FA (django-allauth) |
| `/admin/` | Admin de Django (solo equipo con 2FA) |

Roles: Administradora, Colaboradora, Cliente aprobador y Cliente lector. Qué puede hacer cada uno está en el
**Manual de administración por rol** (`Evidencias de documentación/Documentos generales/Manual-Administracion-Cosmopolitan.docx`).

## Flujo comercial (funcional)

1. Un visitante completa `/cotizacion/` → se crea un **prospecto** (tabla `prospectos`) con plan sugerido por reglas.
2. En `/panel/prospectos/<id>/` el equipo lo gestiona: etapa, responsable, interacciones, Instagram,
   **diagnóstico con IA** (requiere `AI_API_KEY` de Google Gemini en `.env`; el borrador siempre se revisa) y
   «Convertir en cliente».
3. «Crear cotización» arma un borrador con precios del catálogo; se edita, se imprime/guarda como PDF desde el navegador
   y se marca enviada → aceptada/rechazada. Los KPIs del dashboard salen de estas cotizaciones.

El panel exige usuario del equipo (administradora o colaboradora, con 2FA activo) y el portal, un usuario con rol de cliente.
Cada cliente ve solo sus datos; las colaboradoras ven solo los clientes que se les asignaron.

## Estado actual

Panel y portal leen y escriben en la base de datos (Supabase PostgreSQL en producción, SQLite en local):
prospectos y cotizaciones, clientes, calendario editorial con versiones y aprobación del cliente, cumplimiento del plan,
solicitudes, métricas cargadas por archivo CSV o Excel, reportes mensuales en PDF, usuarios con invitación y 2FA, y auditoría.
La integración automática con la API de Meta no forma parte de lo entregado.
En el sitio público quedan algunos textos fijos (portada, estadísticas, sobre nosotras), marcados en los templates con
`TODO: Supabase`; el catálogo de planes y servicios, el contenido de novedades y los datos de contacto sí se editan desde el panel.

Para entrar al admin, crear una cuenta: `.\.venv\Scripts\python.exe manage.py createsuperuser`

## Tests

```powershell
.\.venv\Scripts\python.exe manage.py test apps
```

`manage.py test` usa `config/settings/test.py` (SQLite en memoria): nunca crea bases en Supabase.

## Despliegue en Vercel

En Vercel se importa el repositorio de GitHub con **Root Directory = `plataforma`** y Framework Preset «Other».
`vercel.json` envía todas las rutas a `api/index.py`, que carga Django con `config/settings/prod.py`: DEBUG apagado,
cookies seguras, estáticos servidos por WhiteNoise sin `collectstatic` y tareas de Celery ejecutadas en el momento
(no hay worker). Vercel instala solo `requirements.txt`; desarrollo y tests usan `requirements-dev.txt`.

Plan B en Render (Web Service, Root Directory `plataforma`): build `pip install -r requirements.txt`, start
`gunicorn config.wsgi:application`, mismas variables con `ALLOWED_HOSTS=.onrender.com` y
`CSRF_TRUSTED_ORIGINS=https://*.onrender.com`.

Variables de entorno del proyecto en Vercel (Settings → Environment Variables):

| Variable | Valor |
|---|---|
| `SECRET_KEY` | Una clave larga y nueva (no la de desarrollo) |
| `DATABASE_URL` | La del pooler de Supabase (`...pooler.supabase.com`), idealmente en modo transacción (puerto 6543) |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL`, `AWS_S3_REGION_NAME` | Supabase Storage (documentos y CMS) |
| `AI_API_KEY` | Clave de Gemini (opcional). Para que sea gratis, el proyecto de Google AI Studio de la clave **no** debe tener facturación vinculada |
| `GROQ_API_KEY`, `OPENROUTER_API_KEY` | Respaldo gratuito si Gemini se queda sin cuota (opcionales). Orden en `AI_PROVEEDORES` (por defecto `gemini,groq,openrouter`); modelos en `GROQ_MODEL` y `OPENROUTER_MODEL` |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | Solo si se usa un dominio propio. Sin ellas se aceptan solo las URLs de este proyecto que entrega Vercel (no cualquier `*.vercel.app`) |
| `EXIGIR_2FA_EQUIPO` | No definirla (queda en `True`). Solo en una emergencia, `False` desactiva el 2FA obligatorio del equipo |

No copiar `DEBUG` ni `ALLOWED_HOSTS=localhost` del `.env` local. Las migraciones se aplican desde un equipo local
(`manage.py migrate` con el `DATABASE_URL` de Supabase), no en Vercel. Al terminar, `migrate` también crea la tabla de
la caché compartida (límites de intentos de inicio de sesión) y activa RLS en las tablas de Supabase para que su API
pública no pueda leerlas (ver `apps/core/seguridad_bd.py`).
Los correos de notificación que fallan quedan pendientes y se reintentan solos en el siguiente aviso; también se pueden
reintentar con `python manage.py reintentar_correos` (y revisar en el admin, «Correos salientes»). Mientras no haya proveedor de correo,
los correos quedan en los logs de Vercel.

## Notas

- Los PDF del reporte mensual se generan con fpdf2 (Python puro), sin dependencias del sistema.
- `config/settings/prod.py` es el de producción (Vercel); `dev.py` el local y `test.py` el de los tests.
