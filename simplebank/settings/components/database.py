"""Database configuration, derived from DATABASE_URL."""

from .config import get_settings


def get_databases() -> dict:
    """Build Django's DATABASES dict from the configured DATABASE_URL."""
    url = get_settings().database_url
    host_info = url.hosts()[0]
    return {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': (url.path or '').lstrip('/'),
            'USER': host_info['username'],
            'PASSWORD': host_info['password'],
            'HOST': host_info['host'],
            'PORT': host_info['port'] or 5432,
        },
    }
