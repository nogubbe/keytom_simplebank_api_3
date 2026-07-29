"""Smoke tests verifying the project boots and serves basic routes."""

import pytest


@pytest.mark.django_db
def test_health_endpoint(client):
    """The health endpoint responds with a 200 and an ok status."""
    response = client.get('/api/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_admin_login_page_loads(client):
    """The Django admin login page renders successfully."""
    response = client.get('/admin/login/')

    assert response.status_code == 200
