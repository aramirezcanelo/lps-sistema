# LPS · Portal del equipo

Aplicación web de LPS construida con Django. Usa SQLite para la base de datos, Docker para ejecutar el servicio y un disco persistente de Render para conservar la base y los archivos de Drive.

## Funcionalidad

- Acceso con cuentas aprobadas, roles y sesiones protegidas.
- Finanzas: compras, ingresos, edición, eliminación y reportes XLSX.
- Proyectos: fechas, inventario y notas compartidas.
- Drive: carga múltiple, vista previa, reemplazo, papelera, restauración y descarga.
- Áreas de presidencia y recursos humanos con permisos según rol.

## Requisitos

- Git y una cuenta de GitHub.
- Docker Desktop para desarrollo local.
- Una cuenta de Render.
- Python 3.14 si vas a ejecutar las pruebas directamente en tu equipo.

## Preparar y ejecutar localmente con Docker

1. Copia `.env.example` como `.env`. Cambia `SESSION_SECRET`, `ADMIN_USER` y `ADMIN_PASSWORD`; usa una contraseña de al menos 10 caracteres. El archivo `.env` está ignorado por Git.
2. Construye y arranca la aplicación:

   ```powershell
   docker compose --env-file .env.example up --build -d
   ```

   En el primer arranque, el contenedor aplica migraciones y crea el administrador usando las variables del archivo `.env`. La base y los archivos se guardan en el volumen Docker `lps_data`.
3. Abre <http://localhost:8080/login> y revisa el estado del servicio:

   ```powershell
   docker compose --env-file .env.example logs -f web
   docker compose --env-file .env.example ps
   ```

Para detener la aplicación y conservar los datos:

```powershell
docker compose --env-file .env.example down
```

Para borrar deliberadamente la base local y los archivos del volumen de desarrollo:

```powershell
docker compose --env-file .env.example down --volumes
```

Ese último comando elimina permanentemente los datos del volumen local.

## Ejecutar las pruebas antes de publicar

Las pruebas se conservan en el repositorio como código de verificación, pero `.dockerignore` las excluye de la imagen final. Para ejecutarlas localmente, activa el entorno Python e instala `requirements.txt`; usa una base SQLite temporal:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:DATABASE_URL = "sqlite:///test-run.sqlite3"
python manage.py test core
python manage.py check
python manage.py makemigrations --check --dry-run
Remove-Item Env:DATABASE_URL
```

Las pruebas de Django crean y destruyen su propia base de pruebas. No usan ni vacían tu base local.

## Publicar el repositorio en GitHub manualmente

1. Confirma que `.env`, bases SQLite, `.venv`, `.vscode`, archivos de `data/assets`, `staticfiles` y `MD/` estén excluidos por `.gitignore`.
2. En GitHub, crea el repositorio `aramirezcanelo/lps-sistema`. Déjalo vacío; no agregues README, licencia ni `.gitignore` desde la web para evitar dos historiales iniciales.
3. Desde PowerShell, en la carpeta raíz del proyecto, prepara y revisa el primer commit:

   ```powershell
   git init
   git branch -M main
   git add .
   git diff --cached --check
   git status --short
   git diff --cached --stat
   git diff --cached --name-only
   ```

   Revisa la lista antes de continuar: no debe incluir `.env`, datos locales, archivos subidos ni `MD/`. Si aparece algo indebido, quítalo del staging con `git restore --staged RUTA` y ajusta `.gitignore`.
4. Crea el commit inicial y conecta el remoto:

   ```powershell
   git commit -m "Prepare LPS Django deployment with Docker"
   git remote add origin https://github.com/aramirezcanelo/lps-sistema.git
   git push -u origin main
   ```

   Si `origin` ya existe, compruébalo con `git remote -v` y actualízalo con `git remote set-url origin https://github.com/aramirezcanelo/lps-sistema.git` en vez de agregarlo de nuevo.

## Desplegar en Render

El archivo `render.yaml` describe un servicio Docker y un disco persistente de 1 GB. La aplicación guarda en ese disco `lps.sqlite3` y los archivos de Drive. El plan `starter` y el disco son recursos de pago; revisa el costo mostrado por Render antes de aplicar el Blueprint. Un disco persistente se limita a una instancia y desactiva los despliegues sin interrupción; SQLite también está pensado para un servicio de una sola instancia.

1. Confirma que el commit ya está en GitHub y que el repositorio contiene `Dockerfile`, `docker-entrypoint.sh`, `render.yaml`, `.dockerignore` y `requirements.txt`.
2. En Render, selecciona **New → Blueprint**, conecta la cuenta GitHub y el repositorio `aramirezcanelo/lps-sistema`.
3. Revisa el Blueprint y sus recursos. Render debe detectar `render.yaml`, construir la imagen Docker, crear el disco y solicitar los valores secretos `ADMIN_USER` y `ADMIN_PASSWORD`. Introduce un nombre de administrador y una contraseña fuerte; no escribas secretos en GitHub.
4. Aplica el Blueprint. Al iniciar, el contenedor aplica migraciones en SQLite y crea el administrador inicial. El sitio queda disponible en el dominio `onrender.com` mostrado por Render. La aplicación detecta ese hostname automáticamente para `ALLOWED_HOSTS` y CSRF.
5. Abre `/login`, inicia sesión y valida las páginas de finanzas, proyectos y Drive. Revisa los logs del servicio en Render y confirma que la persistencia funciona cargando un archivo y verificándolo después de un nuevo deploy.
6. Si agregas un dominio personalizado, añade su hostname a `ALLOWED_HOSTS` y su origen `https://...` a `CSRF_TRUSTED_ORIGINS` en las variables del servicio. Mantén `DEBUG=false`, `COOKIE_SECURE=true` y `SECURE_SSL_REDIRECT=true`. Habilita HSTS después de confirmar HTTPS en todos los dominios usados.

### Importante sobre SQLite en Render

SQLite es la base seleccionada para este despliegue. El archivo debe permanecer bajo `/var/data`, que es la ruta persistente declarada en el Blueprint; no cambies `DATABASE_URL` a una ruta temporal del contenedor. Mantén una sola instancia y un solo worker. Si más adelante se necesita escalado horizontal o escrituras concurrentes de mayor volumen, habrá que planear una migración de base de datos antes de escalar.

### Datos de pruebas y datos persistentes

Se retiraron del espacio de trabajo las bases auxiliares SQLite creadas para pruebas/verificaciones. `.gitignore` impide versionar otras bases locales y `Dockerfile`/`.dockerignore` evita incluir pruebas, bases, archivos de usuario o requisitos académicos en la imagen. Las pruebas de Django permanecen como código fuente en GitHub para auditoría; no son datos de prueba. El volumen de Render comienza vacío, salvo los catálogos mínimos creados por las migraciones y la cuenta administrativa inicial.

## Documentación disponible en el repositorio

- [Manual de instalación](docs/installation_manual.md)
- [Manual de usuario](docs/user_manual.md)

La carpeta `MD/` contiene material de la clase de base de datos y está excluida intencionalmente de la publicación de LPS.
