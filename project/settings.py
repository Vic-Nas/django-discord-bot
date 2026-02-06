import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-this-in-production')

DEBUG = os.getenv('DEBUG', 'False') == 'True'

# ALLOWED_HOSTS - include Railway and localhost for development
allowed_hosts_str = os.getenv('ALLOWED_HOSTS', '*.up.railway.app,localhost,127.0.0.1')
app_url = os.getenv('APP_URL', '')

allowed_hosts = [h.strip() for h in allowed_hosts_str.split(',') if h.strip()]
if app_url:
    # Extract hostname from full URL if provided
    if app_url.startswith('http'):
        from urllib.parse import urlparse
        hostname = urlparse(app_url).hostname
        if hostname:
            allowed_hosts.append(hostname)
    else:
        allowed_hosts.append(app_url)

ALLOWED_HOSTS = list(set(allowed_hosts))  # Remove duplicates

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
    # 'project.error_logging_middleware.ErrorLoggingMiddleware',  # TEMPORARILY DISABLED - testing if it causes hang
    # Temporarily disable debug middleware to test if it's causing issues
    # 'project.debug_middleware.DebugRequestMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # Temporarily disable whitenoise to test
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

db_url = os.environ.get('DATABASE_URL')

if db_url:
    parsed_db = dj_database_url.parse(db_url)
else:
    parsed_db = {}

DATABASES = {
    'default': parsed_db
}

# Disable persistent database connections to handle worker fork properly
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

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
)

