"""Tests for the accounts app's services."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User

from simplebank.apps.accounts.enums import TransactionType
from simplebank.apps.accounts.models import Account, Transaction
from simplebank.apps.accounts.services import WELCOME_BONUS, calculate_fee, create_account_for_user


@pytest.mark.django_db
def test_create_account_for_user_sets_welcome_bonus_balance():
    """The new account's balance is the welcome bonus amount."""
    user = User.objects.create_user(username='e@example.com', email='e@example.com')

    account = create_account_for_user(user)

    assert account.balance == WELCOME_BONUS


@pytest.mark.django_db
def test_create_account_for_user_generates_ten_digit_number():
    """The generated account number is exactly 10 digits."""
    user = User.objects.create_user(username='f@example.com', email='f@example.com')

    account = create_account_for_user(user)

    assert len(account.account_number) == 10
    assert account.account_number.isdigit()


@pytest.mark.django_db
def test_create_account_for_user_records_bonus_transaction():
    """A single credit transaction for the welcome bonus is recorded, with no transfer."""
    user = User.objects.create_user(username='g@example.com', email='g@example.com')

    account = create_account_for_user(user)

    transactions = Transaction.objects.filter(account=account)
    assert transactions.count() == 1
    txn = transactions.get()
    assert txn.type == TransactionType.CREDIT
    assert txn.amount == WELCOME_BONUS
    assert txn.transfer is None


@pytest.mark.django_db
def test_create_account_for_user_retries_on_account_number_collision():
    """A collision on the generated account number is retried with a new number."""
    user = User.objects.create_user(username='h@example.com', email='h@example.com')
    other_user = User.objects.create_user(username='i@example.com', email='i@example.com')
    Account.objects.create(user=other_user, account_number='1111111111', balance=Decimal('0.00'))

    with patch(
        'simplebank.apps.accounts.services._generate_account_number',
        side_effect=['1111111111', '2222222222'],
    ):
        account = create_account_for_user(user)

    assert account.account_number == '2222222222'


def test_calculate_fee_uses_percentage_when_above_minimum():
    """2.5% of the amount is used when it exceeds the €5 minimum."""
    assert calculate_fee(Decimal('1000.00')) == Decimal('25.00')


def test_calculate_fee_uses_minimum_when_percentage_is_lower():
    """The €5 minimum fee applies when 2.5% of the amount is smaller."""
    assert calculate_fee(Decimal('100.00')) == Decimal('5.00')


def test_calculate_fee_at_the_boundary_between_percentage_and_minimum():
    """At exactly €200, 2.5% equals the €5 minimum."""
    assert calculate_fee(Decimal('200.00')) == Decimal('5.00')


def test_calculate_fee_rounds_down_below_half():
    """A percentage fee below the half-cent mark rounds down."""
    assert calculate_fee(Decimal('333.33')) == Decimal('8.33')


def test_calculate_fee_rounds_half_up_at_a_tie():
    """A percentage fee landing exactly on a half-cent rounds up (ROUND_HALF_UP)."""
    assert calculate_fee(Decimal('200.20')) == Decimal('5.01')


def test_calculate_fee_on_zero_amount_returns_the_minimum():
    """Characterization test: a zero amount currently still incurs the €5 minimum fee.

    calculate_fee doesn't validate amount > 0 itself — callers (e.g. execute_transfer
    and the transfer API schema) are responsible for rejecting non-positive amounts.
    """
    assert calculate_fee(Decimal('0.00')) == Decimal('5.00')
