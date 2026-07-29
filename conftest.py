import pytest
from testcontainers.community.postgres import PostgresContainer


@pytest.fixture(scope='session')
def django_db_modify_db_settings():
    """Point the test DB at a throwaway Postgres container instead of DATABASE_URL.

    Uses real Postgres (not sqlite) so locking/atomicity behaviour in tests
    matches production, without requiring a manually-run docker-compose stack.
    """
    with PostgresContainer('postgres:17-alpine') as container:
        from django.conf import settings

        settings.DATABASES['default'].update(
            {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': container.dbname,
                'USER': container.username,
                'PASSWORD': container.password,
                'HOST': container.get_container_host_ip(),
                'PORT': container.get_exposed_port(5432),
            },
        )
        yield
