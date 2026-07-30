"""Tests for the users app's HTTP API."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from ninja_jwt.settings import api_settings

from simplebank.apps.accounts.models import Account


@pytest.mark.django_db
def test_register_returns_503_when_account_number_generation_is_exhausted(client, monkeypatch):
    """Registration fails gracefully with 503, not an unhandled 500, when no account number can be generated."""
    monkeypatch.setattr('simplebank.apps.accounts.services._generate_account_number', lambda: '1111111111')
    existing_user = User.objects.create_user(username='existing@example.com', email='existing@example.com')
    Account.objects.create(user=existing_user, account_number='1111111111', balance=Decimal('0.00'))

    response = client.post(
        '/api/auth/register',
        {'email': 'newuser@example.com', 'password': 'a-strong-password-123'},
        content_type='application/json',
    )

    assert response.status_code == 503


@pytest.mark.django_db
def test_register_rejects_a_weak_password_with_422(client):
    """A weak/short password is rejected with 422 and a validator-derived detail message."""
    response = client.post(
        '/api/auth/register',
        {'email': 'weak-http@example.com', 'password': '123'},
        content_type='application/json',
    )

    assert response.status_code == 422
    assert response.json()['detail']


@pytest.mark.django_db
def test_register_rejects_email_longer_than_the_username_column_allows(client):
    """An email longer than auth_user.username's 150-char limit is rejected with 422, not a 500.

    `register_user` stores the email as the `username` too (`User(username=email, email=email)`),
    but `User.email` allows up to 254 chars while `User.username` allows only 150 - a valid,
    RFC-compliant email in that gap would otherwise reach `user.save()` and blow up.
    """
    domain = ('a' * 60 + '.') * 3 + 'com'
    email = f'user@{domain}'
    assert len(email) > 150

    response = client.post(
        '/api/auth/register',
        {'email': email, 'password': 'a-strong-password-123'},
        content_type='application/json',
    )

    assert response.status_code == 422


@pytest.mark.django_db
def test_refresh_endpoint_issues_an_access_token_usable_on_a_protected_endpoint(client):
    """A refresh token from /auth/login can be exchanged for a working access token."""
    client.post(
        '/api/auth/register',
        {'email': 'refresher@example.com', 'password': 'a-strong-password-123'},
        content_type='application/json',
    )
    login_response = client.post(
        '/api/auth/login',
        {'email': 'refresher@example.com', 'password': 'a-strong-password-123'},
        content_type='application/json',
    )
    refresh_token = login_response.json()['refresh']

    refresh_response = client.post(
        '/api/auth/token/refresh',
        {'refresh': refresh_token},
        content_type='application/json',
    )

    assert refresh_response.status_code == 200
    body = refresh_response.json()
    assert set(body) == {'access', 'refresh'}
    protected_response = client.get(
        '/api/accounts/balance',
        headers={'Authorization': f'Bearer {body["access"]}'},
    )
    assert protected_response.status_code == 200


@pytest.mark.django_db
def test_refresh_endpoint_rejects_a_malformed_refresh_token(client):
    """A refresh token that is not a valid JWT is rejected with 401, not a 500."""
    response = client.post(
        '/api/auth/token/refresh',
        {'refresh': 'not-a-token'},
        content_type='application/json',
    )

    assert response.status_code == 401


def test_access_token_lifetime_is_long_enough_to_be_usable():
    """The access token lifetime is configured explicitly, not left at the 5-minute default."""
    assert timedelta(minutes=15) <= api_settings.ACCESS_TOKEN_LIFETIME
    assert timedelta(days=1) <= api_settings.REFRESH_TOKEN_LIFETIME
