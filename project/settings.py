import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

print("[DJANGO_SETTINGS] Starting settings.py load", flush=True)
sys.stdout.flush()

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-this-in-production')

DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
]

MIDDLEWARE = [
    'project.debug_middleware.DebugRequestMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # Temporarily disable whitenoise to see if that's causing the hang
    # 'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'project.wsgi.application'

print("[DJANGO_SETTINGS] Building database config", flush=True)
sys.stdout.flush()

db_url = os.environ.get('DATABASE_URL')
print(f"[DJANGO_SETTINGS] DATABASE_URL present: {bool(db_url)}", flush=True)
sys.stdout.flush()

if db_url:
    print(f"[DJANGO_SETTINGS] DATABASE_URL starts with: {db_url[:20]}...", flush=True)
    sys.stdout.flush()

print("[DJANGO_SETTINGS] Parsing database URL with dj_database_url", flush=True)
sys.stdout.flush()

try:
    parsed_db = dj_database_url.parse(db_url)
    print("[DJANGO_SETTINGS] Database URL parsed successfully", flush=True)
    sys.stdout.flush()
except Exception as e:
    print(f"[DJANGO_SETTINGS] ERROR parsing database URL: {e}", flush=True)
    sys.stdout.flush()
    raise

DATABASES = {
    'default': parsed_db
}

print(f"[DJANGO_SETTINGS] Database config: {DATABASES['default'].get('ENGINE', 'unknown')}", flush=True)
sys.stdout.flush()

# Disable persistent database connections to handle worker fork properly
print("[DJANGO_SETTINGS] Disabling persistent connections", flush=True)
sys.stdout.flush()

DATABASES['default']['CONN_MAX_AGE'] = 0
DATABASES['default']['AUTOCOMMIT'] = True

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Temporarily disable CompressedManifestStaticFilesStorage to see if that's causing hang
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
# STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

import cloudinary

print("[DJANGO_SETTINGS] Configuring Cloudinary", flush=True)
sys.stdout.flush()

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
)

print("[DJANGO_SETTINGS] Cloudinary configured", flush=True)
sys.stdout.flush()


print("[DJANGO_SETTINGS] Settings.py loaded successfully", flush=True)
sys.stdout.flush()

