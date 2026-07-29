"""Tests for the accounts app's HTTP API."""

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from ninja_jwt.tokens import RefreshToken

from simplebank.apps.users.services import register_user


@pytest.fixture
def registered_user(db):
    """Register a user for use in API tests."""
    return register_user('k@example.com', 'a-strong-password-123')


@pytest.fixture
def auth_headers(registered_user):
    """Build an Authorization header with a valid JWT access token."""
    refresh: RefreshToken = RefreshToken.for_user(registered_user)  # type: ignore[assignment,misc]
    return {'Authorization': f'Bearer {refresh.access_token}'}


def test_balance_requires_authentication(client):
    """The balance endpoint returns 401 without a token."""
    response = client.get('/api/accounts/balance')

    assert response.status_code == 401


@pytest.mark.django_db
def test_balance_returns_account_number_and_balance(client, registered_user, auth_headers):
    """The balance endpoint returns the authenticated user's account number and balance."""
    response = client.get('/api/accounts/balance', headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body['account_number'] == registered_user.account.account_number
    assert Decimal(body['balance']) == Decimal('10000.00')


@pytest.mark.django_db
def test_balance_for_user_without_account_returns_404(client):
    """A JWT-authenticated user with no Account (e.g. created via createsuperuser) gets 404."""
    user = User.objects.create_user(username='no-account@example.com', email='no-account@example.com')
    refresh: RefreshToken = RefreshToken.for_user(user)  # type: ignore[assignment,misc]
    headers = {'Authorization': f'Bearer {refresh.access_token}'}

    response = client.get('/api/accounts/balance', headers=headers)

    assert response.status_code == 404
