import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv('DJANGO_DEBUG', '0') == '1'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    raise ImproperlyConfigured('Define DJANGO_SECRET_KEY antes de iniciar Django.')
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
CSRF_TRUSTED_ORIGINS = list(filter(None, os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',')))
INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'dashboard', 'scraper',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'dashboard.accounts.PasswordChangeRequiredMiddleware',
]
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request', 'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
if os.getenv('DB_HOST'):
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql', 'HOST': os.environ['DB_HOST'],
        'PORT': os.getenv('DB_PORT', '5432'), 'NAME': os.getenv('POSTGRES_DB', 'tokendash'),
        'USER': os.getenv('POSTGRES_USER', 'tokendash'), 'PASSWORD': os.environ['POSTGRES_PASSWORD'],
    }}
else:
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3', 'OPTIONS': {'timeout': 20}}}
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
    {'NAME': 'dashboard.accounts.NotDefaultPasswordValidator'},
]
LANGUAGE_CODE = 'es'
TIME_ZONE = os.getenv('TIME_ZONE', 'Europe/Madrid')
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = os.getenv('DJANGO_SECURE_COOKIES', '0') == '1'
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_CONTENT_TYPE_NOSNIFF = True
if os.getenv('DJANGO_TRUST_PROXY_HEADERS', '0') == '1':
    # Only enable when a trusted reverse proxy overwrites this header and clients
    # cannot reach the backend directly. Needed for correct HTTPS callback/setup URLs.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
X_FRAME_OPTIONS = 'DENY'
SCRAPE_INTERVAL_MINUTES = int(os.getenv('SCRAPE_INTERVAL_MINUTES', '20'))
if SCRAPE_INTERVAL_MINUTES < 15:
    raise ImproperlyConfigured('El intervalo mínimo es de 15 minutos.')
# The server reads Claude's subscription limits with the official client itself.
# The client authenticates with the claude.ai session kept in its own configuration directory.
CLAUDE_CLIENT_PATH = os.getenv('CLAUDE_CLIENT_PATH', '')
CLAUDE_CLIENT_TIMEOUT = int(os.getenv('CLAUDE_CLIENT_TIMEOUT', '40'))
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_IGNORE_RESULT = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_PUBLISH_RETRY = False
CELERY_BROKER_CONNECTION_TIMEOUT = 3
CELERY_TASK_SOFT_TIME_LIMIT = 150
CELERY_TASK_TIME_LIMIT = 180
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {'refresh-providers': {
    'task': 'scraper.tasks.refresh_all', 'schedule': SCRAPE_INTERVAL_MINUTES * 60,
    'options': {'expires': SCRAPE_INTERVAL_MINUTES * 60},
}}
LOGGING = {'version': 1, 'disable_existing_loggers': False,
           'handlers': {'console': {'class': 'logging.StreamHandler'}},
           'root': {'handlers': ['console'], 'level': 'INFO'}}
