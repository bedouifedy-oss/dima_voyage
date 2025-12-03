"""
Django settings for config project.
"""

import os
from pathlib import Path

import dj_database_url
import sentry_sdk
from django.templatetags.static import static
from django.urls import reverse_lazy
from sentry_sdk.integrations.django import DjangoIntegration

# Initialize Sentry ONLY if a DSN is provided in .env
SENTRY_DSN = os.environ.get("SENTRY_DSN")

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=1.0,
        send_default_pii=True,
    )

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-fallback-key")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DEBUG") == "True"

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost").split(",")


# Application definition

INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "simple_history",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rangefilter",
    "core.apps.CoreConfig",
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
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL", "sqlite:///db.sqlite3"), conn_max_age=600
    )
}


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

STATICFILES_DIRS = [
    BASE_DIR / "assets",
    BASE_DIR / "core" / "static",
]

STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- UNFOLD CONFIGURATION (SAFE MODE) ---
# Removed all lambdas and permissions to guarantee load
UNFOLD = {
    "SITE_TITLE": "Dima Voyage",
    "SITE_HEADER": "Dima Admin",
    "SITE_URL": "/",
    "SITE_ICON": "/static/dima_voyages.png",
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Operations",
                "separator": True,
                "items": [
                    {
                        "title": "Bookings",
                        "icon": "airplane_ticket",
                        "link": "/admin/core/booking/",
                    },
                    {
                        "title": "Clients",
                        "icon": "group",
                        "link": "/admin/core/client/",
                    },
                    {
                        "title": "Visa Applications",
                        "icon": "badge",
                        "link": "/admin/core/visaapplication/",
                    },
                    {
                        "title": "Suppliers",
                        "icon": "store",
                        "link": "/admin/core/supplier/",
                    },
                ],
            },
            {
                "title": "Finance",
                "separator": True,
                "items": [
                    {
                        "title": "Payments",
                        "icon": "payments",
                        "link": "/admin/core/payment/",
                    },
                    {
                        "title": "Ledger (Cash Flow)",
                        "icon": "account_balance",
                        "link": "/admin/core/ledgerentry/",
                    },
                    {
                        "title": "Expenses",
                        "icon": "receipt_long",
                        "link": "/admin/core/expense/",
                    },
                ],
            },
            {
                "title": "Support & Updates",
                "separator": True,
                "items": [
                    {
                        "title": "Announcements",
                        "icon": "campaign",
                        "link": "/admin/core/announcement/",
                        "badge": "core.utils.badge_callback",
                    },
                    {
                        "title": "Knowledge Base",
                        "icon": "menu_book",
                        "link": "/admin/core/knowledgebase/",
                    },
                ],
            },
        ],
    },
}

# --- SECURITY HARDENING ---
if not DEBUG:
    # Disabled for IP Access
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = "DENY"
