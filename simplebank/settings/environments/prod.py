"""Production settings. Secrets and hosts must come from the environment."""

from ..components.common import *
from ..components.common import settings
from ..components.database import get_databases
from ..components.security import *

DEBUG = False

ALLOWED_HOSTS = settings.allowed_hosts

DATABASES = get_databases()
