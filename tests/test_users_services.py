"""Tests for the users app's services."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User

from simplebank.apps.accounts.enums import TransactionType
from simplebank.apps.accounts.models import Transaction
from simplebank.apps.users.exceptions import EmailAlreadyRegisteredError, WeakPasswordError
from simplebank.apps.users.services import register_user


@pytest.mark.django_db
def test_register_user_creates_account_with_welcome_bonus():
    """Registering a user also creates their bank account with the welcome bonus."""
    user = register_user('j@example.com', 'a-strong-password-123')

    assert user.account.balance == Decimal('10000.00')
    assert Transaction.objects.filter(account=user.account, type=TransactionType.CREDIT).count() == 1


@pytest.mark.django_db
def test_register_user_converts_concurrent_duplicate_email_to_email_already_registered_error():
    """A duplicate-username IntegrityError from a concurrent registration surfaces as EmailAlreadyRegisteredError.

    The pre-check (`User.objects.filter(email=...).exists()`) is not atomic with the insert, so a
    same-email registration racing in another request can slip past it. Simulate that race by
    forcing the pre-check to report no match, exactly as it would if the other request's insert
    hadn't committed yet when this check ran.
    """
    register_user('race@example.com', 'a-strong-password-123')

    with patch('simplebank.apps.users.services.User.objects.filter') as mock_filter:
        mock_filter.return_value.exists.return_value = False
        with pytest.raises(EmailAlreadyRegisteredError):
            register_user('race@example.com', 'another-strong-password-456')


@pytest.mark.django_db
def test_register_user_rejects_a_weak_password_with_a_typed_error():
    """A password failing Django's validators raises WeakPasswordError, not a bare ValueError."""
    with pytest.raises(WeakPasswordError) as exc_info:
        register_user('weak@example.com', '123')

    assert exc_info.value.messages
    assert not User.objects.filter(email='weak@example.com').exists()
