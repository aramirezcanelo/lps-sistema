# Manual de instalación

## Requisitos

- Docker Desktop y Docker Compose.
- Git para publicar el repositorio.
- Render para el despliegue.

## Inicio local

1. Copia `.env.example` a `.env`.
2. Cambia `SESSION_SECRET`, `ADMIN_USER` y `ADMIN_PASSWORD` en `.env`.
3. Construye y arranca el contenedor:

   ```powershell
   docker compose --env-file .env.example up --build -d
   ```

4. Abre <http://localhost:8080/login>. Las migraciones y la cuenta inicial se preparan en el primer inicio.

La base local SQLite y los archivos de Drive se guardan en el volumen Docker `lps_data`. `docker compose --env-file .env.example down` conserva los datos. `docker compose --env-file .env.example down --volumes` los borra permanentemente.

## Ejecutar pruebas

Las pruebas permanecen en el repositorio como código y corren fuera de la imagen de producción:

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

El runner de Django crea y destruye su base temporal de pruebas. Las bases locales se excluyen de Git.

## Publicar en GitHub

1. Crea un repositorio vacío en GitHub con el nombre `lps-sistema` bajo `aramirezcanelo`.
2. Revisa `git status --ignored` y confirma que `.env`, bases SQLite, `data/assets`, `staticfiles`, `.venv`, `.vscode` y `MD/` estén excluidos.
3. Inicializa, revisa y publica el primer commit:

   ```powershell
   git init
   git branch -M main
   git add .
   git diff --cached --check
   git status --short
   git diff --cached --stat
   git diff --cached --name-only
   git commit -m "Prepare LPS Django deployment with Docker"
   git remote add origin https://github.com/aramirezcanelo/lps-sistema.git
   git push -u origin main
   ```

Si el remoto ya existe, revisa `git remote -v` y usa `git remote set-url origin https://github.com/aramirezcanelo/lps-sistema.git` en lugar de `git remote add`.

## Desplegar en Render

1. En Render selecciona **New → Blueprint**, conecta GitHub y selecciona `aramirezcanelo/lps-sistema`.
2. Revisa los recursos que aparecen desde `render.yaml`. El servicio Docker usa un plan pagado porque SQLite y los archivos necesitan un disco persistente de Render. Confirma el precio antes de aplicar.
3. Cuando Render solicite `ADMIN_USER` y `ADMIN_PASSWORD`, ingresa los valores secretos en Render, nunca en el repositorio.
4. Aplica el Blueprint. En el primer inicio, el contenedor ejecuta migraciones, prepara la cuenta administrativa y levanta Gunicorn.
5. Abre el dominio HTTPS generado, valida `/login`, y comprueba que una carga de Drive siga disponible después de un deploy posterior.

El Blueprint usa `/var/data/lps.sqlite3` para SQLite y `/var/data/assets` para archivos. Ambos quedan dentro del disco persistente. Mantén una sola instancia y el único worker configurado. SQLite no debe compartirse entre réplicas. Para un dominio personalizado, agrega su hostname a `ALLOWED_HOSTS` y su origen HTTPS a `CSRF_TRUSTED_ORIGINS`.
