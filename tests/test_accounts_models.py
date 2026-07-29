"""Tests for the accounts app's models."""

from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from simplebank.apps.accounts.enums import TransactionType
from simplebank.apps.accounts.models import Account, Transaction, Transfer


@pytest.mark.django_db
def test_account_str_returns_account_number():
    """Account.__str__ returns the account number."""
    user = User.objects.create_user(username='a@example.com', email='a@example.com')
    account = Account.objects.create(user=user, account_number='1234567890', balance=Decimal('10000.00'))

    assert str(account) == '1234567890'


@pytest.mark.django_db
def test_transaction_transfer_is_nullable():
    """A Transaction can exist without an associated Transfer (welcome bonus case)."""
    user = User.objects.create_user(username='b@example.com', email='b@example.com')
    account = Account.objects.create(user=user, account_number='1234567891', balance=Decimal('10000.00'))

    txn = Transaction.objects.create(account=account, type=TransactionType.CREDIT, amount=Decimal('10000.00'))

    assert txn.transfer is None


@pytest.mark.django_db
def test_transfer_links_two_distinct_accounts():
    """A Transfer references a sender and a receiver account."""
    sender_user = User.objects.create_user(username='c@example.com', email='c@example.com')
    receiver_user = User.objects.create_user(username='d@example.com', email='d@example.com')
    sender = Account.objects.create(user=sender_user, account_number='1234567892', balance=Decimal('10000.00'))
    receiver = Account.objects.create(user=receiver_user, account_number='1234567893', balance=Decimal('10000.00'))

    transfer = Transfer.objects.create(
        sender_account=sender,
        receiver_account=receiver,
        amount=Decimal('100.00'),
        fee=Decimal('5.00'),
    )

    assert transfer.sender_account_id == sender.pk
    assert transfer.receiver_account_id == receiver.pk


@pytest.mark.django_db
def test_transfer_total_debited_is_amount_plus_fee():
    """Transfer.total_debited sums amount and fee."""
    sender_user = User.objects.create_user(username='m@example.com', email='m@example.com')
    receiver_user = User.objects.create_user(username='n@example.com', email='n@example.com')
    sender = Account.objects.create(user=sender_user, account_number='1234567894', balance=Decimal('10000.00'))
    receiver = Account.objects.create(user=receiver_user, account_number='1234567895', balance=Decimal('10000.00'))

    transfer = Transfer.objects.create(
        sender_account=sender,
        receiver_account=receiver,
        amount=Decimal('100.00'),
        fee=Decimal('5.00'),
    )

    assert transfer.total_debited == Decimal('105.00')
