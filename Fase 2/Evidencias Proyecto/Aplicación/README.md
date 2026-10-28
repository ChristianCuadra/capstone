# Evidencias Proyecto · Aplicación

**`Plataforma-Cosmopolitan-codigo.zip`** contiene el código fuente completo de la plataforma (carpeta `plataforma/`), comprimido desde la rama `main`. Incluye solo los archivos versionados en git: no trae el archivo `.env` con credenciales, el entorno virtual ni bases de datos locales. Las variables necesarias están descritas en `plataforma/.env.example`.

El código vivo sigue en la carpeta [`plataforma/`](../../../plataforma) de la raíz del repositorio, que es la que usan GitHub Actions (pruebas automáticas) y Vercel (despliegue). Para levantarla en local, ver `plataforma/README.md` (dentro del zip o en la raíz).

Cuando el código cambie, el zip se regenera con:

```
git archive --format=zip -9 --prefix=plataforma/ -o "Fase 2/Evidencias Proyecto/Aplicación/Plataforma-Cosmopolitan-codigo.zip" HEAD:plataforma
```
