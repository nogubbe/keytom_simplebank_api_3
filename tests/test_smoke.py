import pytest


@pytest.mark.django_db
def test_health_endpoint(client):
    response = client.get('/api/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_admin_login_page_loads(client):
    response = client.get('/admin/login/')

    assert response.status_code == 200
