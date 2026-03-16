import os
from pathlib import Path
from datetime import timedelta

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Environment Variables & Security ---

def get_env_or_fail(var_name):
    value = os.environ.get(var_name)
    if not value:
        raise ImproperlyConfigured(f"Environment variable {var_name} is missing.")
    return value

from django.core.exceptions import ImproperlyConfigured

# SECRET_KEY from os.environ['APP_SECRET_KEY'] — fail startup if missing.
SECRET_KEY = get_env_or_fail('APP_SECRET_KEY')

# ENCRYPTION_KEY from env — fail startup if missing. Validate ≥32 bytes.
ENCRYPTION_KEY = get_env_or_fail('ENCRYPTION_KEY')
if len(ENCRYPTION_KEY.encode('utf-8')) < 32:
    raise ImproperlyConfigured("ENCRYPTION_KEY must be at least 32 bytes.")

# ALLOWED_HOSTS from env (comma-split).
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',')
if not ALLOWED_HOSTS or ALLOWED_HOSTS == ['']:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']

DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

# --- Application definition ---

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'axes',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
    'core.middleware.security.SecurityHeadersMiddleware',
    'core.middleware.setup.FirstRunMiddleware',
]

SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

ROOT_URLCONF = 'twitterbot.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'twitterbot.wsgi.application'

# --- Database ---
# SQLite at /app/data/db.sqlite3 per requirements
# Using BASE_DIR / 'data' / 'db.sqlite3' for local development as well if /app doesn't exist
DB_PATH = os.environ.get('DB_PATH', str(BASE_DIR / 'data' / 'db.sqlite3'))
db_dir = os.path.dirname(DB_PATH)
if db_dir:
    os.makedirs(db_dir, exist_ok=True)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DB_PATH,
    }
}

# --- Password validation ---

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# --- Internationalization ---

LANGUAGE_CODE = 'en-us'

# TIME_ZONE from env TZ, default UTC.
TIME_ZONE = os.environ.get('TZ', 'UTC')

USE_I18N = True

USE_TZ = True

# --- Static files ---

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

import sys
if 'test' in sys.argv:
    STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.StaticFilesStorage"
    WHITENOISE_MANIFEST_STRICT = False

# --- Security Settings ---

CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True

# Based on env flag for production/staging
IS_SECURE = os.environ.get('IS_SECURE', 'False').lower() == 'true'
SESSION_COOKIE_SECURE = IS_SECURE
CSRF_COOKIE_SECURE = IS_SECURE

# SEC-INPUT-002: Request body size limit
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5MB

# --- django-axes Configuration ---

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)

# --- Tweet Settings ---

TWEET_MIN_LENGTH = int(os.environ.get('TWEET_MIN_LENGTH', 1))
TWEET_MAX_LENGTH = int(os.environ.get('TWEET_MAX_LENGTH', 280))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'core:login'
LOGIN_REDIRECT_URL = 'core:dashboard'
LOGOUT_REDIRECT_URL = 'core:login'

