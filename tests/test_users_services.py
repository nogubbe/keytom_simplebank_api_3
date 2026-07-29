"""Tests for the users app's services."""

from decimal import Decimal

import pytest

from simplebank.apps.accounts.enums import TransactionType
from simplebank.apps.accounts.models import Transaction
from simplebank.apps.users.services import register_user


@pytest.mark.django_db
def test_register_user_creates_account_with_welcome_bonus():
    """Registering a user also creates their bank account with the welcome bonus."""
    user = register_user('j@example.com', 'a-strong-password-123')

    assert user.account.balance == Decimal('10000.00')
    assert Transaction.objects.filter(account=user.account, type=TransactionType.CREDIT).count() == 1
