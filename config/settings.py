"""SSB Group platform settings. All secrets and environment-specific values come from env vars."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

DEBUG = env.bool("DJANGO_DEBUG", default=False)
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])
SITE_URL = env("SITE_URL", default="http://localhost:8000").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "django.contrib.sitemaps",
    "apps.core",
    "apps.accounts",
    "apps.audit",
    "apps.notifications",
    "apps.website",
    "apps.crm",
    "rest_framework",
    "apps.enterprise",
    "apps.chat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.core.desktop_only.DesktopManagementOnlyMiddleware",  # Windows ilovasida faqat boshqaruv tizimi
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.devices.DeviceSessionMiddleware",
    "apps.enterprise.middleware.RoleStatusMiddleware",
    "apps.enterprise.capability_gate.CapabilityGateMiddleware",
    "apps.enterprise.middleware.ArchiveVisitMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.website.context_processors.site",
                "apps.notifications.context_processors.unread",
                "apps.enterprise.ui.shell",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"]["ATOMIC_REQUESTS"] = True

CACHES = {"default": env.cache("CACHE_URL", default="locmemcache://")}

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "enterprise:overview"
LOGOUT_REDIRECT_URL = "website:home"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_RESET_TIMEOUT = 60 * 60 * 72  # invitation / reset links live 3 days

LANGUAGE_CODE = "uz"
LANGUAGES = [("uz", "O‘zbekcha")]
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        # STATIC_MANIFEST=False (deploy/production.env): compressed files without strict hashed names,
        # so one missing static reference can never take a page down. Templates already add ?v= for cache busting.
        "BACKEND": ("whitenoise.storage.CompressedManifestStaticFilesStorage" if env.bool("STATIC_MANIFEST", default=True)
                    else "whitenoise.storage.CompressedStaticFilesStorage")
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

# Public media (portfolio, team photos) is served at MEDIA_URL.
MEDIA_URL = "/media/"
# An empty value in .env means "use the default", not the current working directory.
MEDIA_ROOT = Path(env("MEDIA_ROOT", default="") or str(BASE_DIR / "media"))
# Private media (task attachments, employee photos) is never served directly;
# it is streamed by permission-checked views only.
PRIVATE_MEDIA_ROOT = Path(env("PRIVATE_MEDIA_ROOT", default="") or str(BASE_DIR / "private_media"))

# Local deploy (deploy/start.bat) has no separate web server, so Django serves the public media folder itself.
SERVE_PUBLIC_MEDIA = env.bool("SERVE_PUBLIC_MEDIA", default=False)

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = 10
EMAIL_NOTIFICATIONS_ENABLED = env.bool('EMAIL_NOTIFICATIONS_ENABLED', default=True)
TELEGRAM_BOT_TOKEN = env('TELEGRAM_BOT_TOKEN', default='')
TELEGRAM_BOT_USERNAME = env('TELEGRAM_BOT_USERNAME', default='')
TELEGRAM_NOTIFICATIONS_ENABLED = env.bool('TELEGRAM_NOTIFICATIONS_ENABLED', default=True)
# Bot asosiy adminlari (Telegram ID, vergul bilan). Ular admin panelni ko'radi va boshqa admin qo'sha oladi.
TELEGRAM_ADMIN_IDS = env('TELEGRAM_ADMIN_IDS', default='')
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="SSB Group <no-reply@localhost>")

# Session & cookie security
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 12
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
    SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=60 * 60 * 24 * 30)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    if env.bool("DJANGO_BEHIND_PROXY", default=False):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Rate limits: (max attempts, window seconds)
LOGIN_RATE_LIMIT = (8, 15 * 60)
INQUIRY_RATE_LIMIT = (5, 60 * 60)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": "%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s",
        },
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "structured"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {"django.db.backends": {"level": "WARNING"}},
}

# Shared enterprise / desktop services. Never ship these secrets in the desktop build.
REST_FRAMEWORK = {"DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"], "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"], "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"], "DEFAULT_THROTTLE_RATES": {"user": "180/min"}}
ARCHIVE_MAX_MB = env.int("ARCHIVE_MAX_MB", default=50)
ARCHIVE_UNPACKED_MAX_MB = env.int("ARCHIVE_UNPACKED_MAX_MB", default=500)
MALWARE_SCANNER = env("MALWARE_SCANNER", default="")
REQUIRE_MALWARE_SCAN = env.bool("REQUIRE_MALWARE_SCAN", default=not DEBUG)
PERFORMANCE_AI_ENDPOINT = env("PERFORMANCE_AI_ENDPOINT", default="")
PERFORMANCE_AI_KEY = env("PERFORMANCE_AI_KEY", default="")
# Haftalik baholash uchun Claude (SSB AI). Kalit bo‘lmasa, ball ochiq formula bo‘yicha hisoblanadi.
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
PERFORMANCE_AI_MODEL = env("PERFORMANCE_AI_MODEL", default="claude-opus-5-5")
# Dushanba 00:00 da o‘tgan haftani avtomatik yopib, reytingni e’lon qilish.
PERFORMANCE_AUTO_CLOSE = env.bool("PERFORMANCE_AUTO_CLOSE", default=True)
DESKTOP_VERSION = '2.0.6'
DESKTOP_RELEASE_PATH = Path(env('DESKTOP_RELEASE_PATH', default=str(BASE_DIR / 'desktop' / 'release' / f'SSB-Boshqaruv-Setup-{DESKTOP_VERSION}.exe')))
