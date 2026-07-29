"""Tests for the users app's HTTP API."""

from decimal import Decimal

import pytest
from django.contrib.auth.models import User

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
