"""Local development settings. Not suitable for production."""

from ..components.common import *
from ..components.common import settings
from ..components.database import get_databases

DEBUG = settings.debug

ALLOWED_HOSTS = settings.allowed_hosts or ['localhost', '127.0.0.1']

DATABASES = get_databases()
