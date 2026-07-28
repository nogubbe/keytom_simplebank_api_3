"""Production-grade transport security settings."""

from .common import settings

SECURE_SSL_REDIRECT = settings.secure_ssl_redirect
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = settings.secure_hsts_seconds
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
