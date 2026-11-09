import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-development-key")
DEBUG = os.getenv("DEBUG", "False").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = [x.strip() for x in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if x.strip()]
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if x.strip()]

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "django_filters",
    "apps.core", "apps.accounts", "apps.orders", "apps.deliverables", "apps.processing", "apps.music",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

db_url = os.getenv("DATABASE_URL", "")
if db_url:
    parsed = urlparse(db_url)
    query = parse_qs(parsed.query)
    database_options = {key: values[-1] for key, values in query.items() if values}
    if parsed.hostname and parsed.hostname.endswith(".pooler.supabase.com"):
        database_options.setdefault("sslmode", os.getenv("DB_SSLMODE", "require"))
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": parsed.port or 5432,
        "CONN_MAX_AGE": int(os.getenv("DATABASE_CONN_MAX_AGE", "60")),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": database_options,
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "Africa/Lagos")
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_BACKEND = (
    "django.contrib.staticfiles.storage.StaticFilesStorage"
    if "test" in sys.argv
    else "whitenoise.storage.CompressedManifestStaticFilesStorage"
)
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": STATICFILES_BACKEND}}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "orders:dashboard"
LOGOUT_REDIRECT_URL = "home"
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "hello@example.com")
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "False").lower() in {"1", "true", "yes"}
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication", "rest_framework.authentication.BasicAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend", "rest_framework.filters.SearchFilter", "rest_framework.filters.OrderingFilter"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination", "PAGE_SIZE": 20,
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.NamespaceVersioning",
}
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_LLM_BASE_URL = os.getenv("NVIDIA_LLM_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_LLM_MODEL = os.getenv("NVIDIA_LLM_MODEL", "nvidia/nvidia-nemotron-nano-9b-v2")
NVIDIA_ASR_SERVER = os.getenv("NVIDIA_ASR_SERVER", "grpc.nvcf.nvidia.com:443")
NVIDIA_ASR_FUNCTION_ID = os.getenv("NVIDIA_ASR_FUNCTION_ID", "d3fe9151-442b-4204-a70d-5fcc597fd610")
NVIDIA_ASR_LANGUAGE = os.getenv("NVIDIA_ASR_LANGUAGE", "en-US")
NVIDIA_IMAGE_API_URL = os.getenv("NVIDIA_IMAGE_API_URL", "")
NVIDIA_IMAGE_MODEL = os.getenv("NVIDIA_IMAGE_MODEL", "stable-diffusion-3.5-large")
NVIDIA_VIDEO_API_URL = os.getenv("NVIDIA_VIDEO_API_URL", "")
NVIDIA_VIDEO_MODEL = os.getenv("NVIDIA_VIDEO_MODEL", "wan-ai/wan2.2")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
FFMPEG_BINARY = os.getenv("FFMPEG_BINARY", "ffmpeg")
FFPROBE_BINARY = os.getenv("FFPROBE_BINARY", "ffprobe")
PIPELINE_ALLOW_MOCK_AI = os.getenv("PIPELINE_ALLOW_MOCK_AI", "True").lower() in {"1", "true", "yes"}
AI_PROVIDER = os.getenv("AI_PROVIDER", "groq").lower()
GROQ_API_KEY = os.getenv("groq_api_key", os.getenv("GROQ_API_KEY", ""))
GROQ_TRANSCRIPTION_MODEL = os.getenv("GROQ_TRANSCRIPTION_MODEL", "whisper-large-v3-turbo")
GROQ_TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "openai/gpt-oss-20b")
GROQ_MAX_COMPLETION_TOKENS = max(1024, min(int(os.getenv("GROQ_MAX_COMPLETION_TOKENS", "4096")), 16384))
PIPELINE_ANALYSIS_ONLY = os.getenv("PIPELINE_ANALYSIS_ONLY", "True").lower() in {"1", "true", "yes"}
PIPELINE_REQUIRE_APPROVAL = os.getenv("PIPELINE_REQUIRE_APPROVAL", "True").lower() in {"1", "true", "yes"}
PIPELINE_EXECUTION_MODE = os.getenv("PIPELINE_EXECUTION_MODE", "thread").lower()
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")
CLOUDINARY_FALLBACK_ENABLED = os.getenv("CLOUDINARY_FALLBACK_ENABLED", "True").lower() in {"1", "true", "yes"}
MEDIA_PIPELINE_PRIMARY = os.getenv("MEDIA_PIPELINE_PRIMARY", "cloudinary").lower()
SUBTITLE_FONT_SIZE = max(8, min(int(os.getenv("SUBTITLE_FONT_SIZE", "11")), 24))
SUBTITLE_MARGIN_V = max(40, min(int(os.getenv("SUBTITLE_MARGIN_V", "90")), 300))
PUBLIC_MEDIA_MAX_BYTES = int(os.getenv("PUBLIC_MEDIA_MAX_BYTES", str(2 * 1024 * 1024 * 1024)))
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60 * 60 * 3
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "False").lower() in {"1", "true", "yes"}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "render": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "render"},
    },
    "loggers": {
        "apps.processing.services.groq_provider": {
            "handlers": ["console"],
            "level": os.getenv("GROQ_LOG_LEVEL", "INFO").upper(),
            "propagate": False,
        },
    },
}
