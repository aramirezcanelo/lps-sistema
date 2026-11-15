import os
from pathlib import Path
from .env import load_env

BASE_DIR = Path(__file__).resolve().parent.parent
load_env(BASE_DIR / ".env")
SECRET_KEY = os.getenv("SESSION_SECRET", "")
if len(SECRET_KEY) < 32:
    raise ValueError("SESSION_SECRET debe tener al menos 32 caracteres")
admin_user, admin_password = os.getenv("ADMIN_USER", "").strip(), os.getenv("ADMIN_PASSWORD", "")
if bool(admin_user) != bool(admin_password):
    raise ValueError("Define ADMIN_USER y ADMIN_PASSWORD juntos")
if admin_password and not 10 <= len(admin_password.encode()) <= 72:
    raise ValueError("ADMIN_PASSWORD debe tener entre 10 y 72 bytes")
# DEBUG conserva el control de seguridad; el servidor local puede activar estáticos aparte.
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
SERVE_STATIC = os.getenv("SERVE_STATIC", "false").lower() == "true"
ALLOWED_HOSTS = [x for x in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if x]
render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if render_hostname:
    ALLOWED_HOSTS.append(render_hostname)
if not DEBUG and not ALLOWED_HOSTS:
    raise ValueError("ALLOWED_HOSTS debe configurarse cuando DEBUG=false")
INSTALLED_APPS = ["django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "core"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware", "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware"]
try:
    import whitenoise  # noqa: F401
except ImportError:
    STATICFILES_BACKEND = "django.contrib.staticfiles.storage.StaticFilesStorage"
else:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    STATICFILES_BACKEND = "whitenoise.storage.CompressedManifestStaticFilesStorage"
ROOT_URLCONF = "lps.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "web" / "templates"], "APP_DIRS": True, "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages", "core.context_processors.modules"]}}]
WSGI_APPLICATION = "lps.wsgi.application"
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://"):
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(DATABASE_URL)
    DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": parsed.path.lstrip("/"), "USER": parsed.username or "", "PASSWORD": parsed.password or "", "HOST": parsed.hostname or "", "PORT": parsed.port or 5432, "OPTIONS": {"sslmode": parse_qs(parsed.query).get("sslmode", ["prefer"])[0]}}}
elif DATABASE_URL.startswith("sqlite:"):
    sqlite_name=DATABASE_URL.removeprefix("sqlite:///") or "db.sqlite3"
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / sqlite_name}}
else:
    raise ValueError("DATABASE_URL debe usar PostgreSQL o sqlite:// para pruebas locales")
AUTH_USER_MODEL = "core.User"
AUTHENTICATION_BACKENDS = ["core.auth.LegacyBackend"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]
SESSION_COOKIE_NAME = "sessionid"
SESSION_COOKIE_AGE = 60 * 60 * 12
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "false").lower() == "true"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
LOGIN_URL = "/login"
LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "web" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": os.getenv("STATICFILES_STORAGE", STATICFILES_BACKEND)}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", str(BASE_DIR / "data" / "assets")))
MEDIA_URL = "/media/"
# Permite el lote máximo (20 archivos de hasta 20 MB); cada archivo se valida
# por separado en la vista de carga de Drive.
DATA_UPLOAD_MAX_MEMORY_SIZE = 420 * 1024 * 1024
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()]
if render_hostname:
    CSRF_TRUSTED_ORIGINS.append(f"https://{render_hostname}")
CSRF_FAILURE_VIEW = "core.views.csrf_failure"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"standard": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "standard"}},
    "loggers": {
        "django": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"), "propagate": False},
        "core": {"handlers": ["console"], "level": os.getenv("APP_LOG_LEVEL", "INFO"), "propagate": False},
    },
}
