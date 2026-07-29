"""Tests for the accounts app's HTTP API."""

from datetime import timedelta
from decimal import Decimal
from http import HTTPStatus

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.utils import timezone
from ninja_jwt.tokens import RefreshToken

from simplebank.apps.accounts.api import transfer
from simplebank.apps.accounts.enums import TransactionType
from simplebank.apps.accounts.models import Transaction
from simplebank.apps.accounts.schemas import TransferInScheme
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


def test_transactions_requires_authentication(client):
    """The transaction history endpoint returns 401 without a token."""
    response = client.get('/api/accounts/transactions')

    assert response.status_code == 401


@pytest.mark.django_db
def test_transactions_for_user_without_account_returns_404(client):
    """A JWT-authenticated user with no Account gets 404, matching the /balance contract."""
    user = User.objects.create_user(username='no-account-history@example.com', email='no-account-history@example.com')
    refresh: RefreshToken = RefreshToken.for_user(user)  # type: ignore[assignment,misc]
    headers = {'Authorization': f'Bearer {refresh.access_token}'}

    response = client.get('/api/accounts/transactions', headers=headers)

    assert response.status_code == 404


@pytest.mark.django_db
def test_transactions_rejects_inverted_date_range(client, registered_user, auth_headers):
    """A `from` date after the `to` date is rejected with 422 rather than silently returning nothing."""
    response = client.get(
        '/api/accounts/transactions',
        {'from': '2030-01-01', 'to': '2020-01-01'},
        headers=auth_headers,
    )

    assert response.status_code == 422


@pytest.mark.django_db
def test_transactions_rejects_invalid_date(client, registered_user, auth_headers):
    """An unparseable `from` value is rejected with 422, not a 500."""
    response = client.get('/api/accounts/transactions', {'from': 'not-a-date'}, headers=auth_headers)

    assert response.status_code == 422


@pytest.mark.django_db
def test_transactions_returns_welcome_bonus(client, registered_user, auth_headers):
    """A freshly registered user's history contains only the welcome-bonus credit."""
    response = client.get('/api/accounts/transactions', headers=auth_headers)

    assert response.status_code == 200
    items = response.json()['items']
    assert len(items) == 1
    assert items[0]['type'] == 'credit'
    assert Decimal(items[0]['amount']) == Decimal('10000.00')


@pytest.mark.django_db
def test_transactions_serializes_debit_type(client, registered_user, auth_headers):
    """A debit transaction serializes with type 'debit', pinning the enum-to-JSON contract."""
    debit = Transaction.objects.create(
        account=registered_user.account,
        type=TransactionType.DEBIT,
        amount=Decimal('1.00'),
    )

    response = client.get('/api/accounts/transactions', headers=auth_headers)

    items = {item['id']: item for item in response.json()['items']}
    assert items[debit.pk]['type'] == 'debit'


@pytest.mark.django_db
def test_transactions_from_filter_excludes_older_entries(client, registered_user, auth_headers):
    """The `from` filter excludes transactions timestamped before the given date, keeps in-range ones."""
    bonus = registered_user.account.transactions.get()
    Transaction.objects.filter(pk=bonus.pk).update(timestamp=timezone.now() - timedelta(days=30))
    recent = Transaction.objects.create(
        account=registered_user.account,
        type=TransactionType.DEBIT,
        amount=Decimal('1.00'),
    )

    params = {'from': timezone.now().date().isoformat()}
    response = client.get('/api/accounts/transactions', params, headers=auth_headers)

    assert response.status_code == 200
    items = response.json()['items']
    assert len(items) == 1
    assert items[0]['id'] == recent.pk


@pytest.mark.django_db
def test_transactions_to_filter_excludes_newer_entries(client, registered_user, auth_headers):
    """The `to` filter excludes transactions timestamped after the given date, keeps in-range ones."""
    bonus = registered_user.account.transactions.get()
    future = Transaction.objects.create(
        account=registered_user.account,
        type=TransactionType.DEBIT,
        amount=Decimal('1.00'),
    )
    Transaction.objects.filter(pk=future.pk).update(timestamp=timezone.now() + timedelta(days=30))

    params = {'to': timezone.now().date().isoformat()}
    response = client.get('/api/accounts/transactions', params, headers=auth_headers)

    assert response.status_code == 200
    items = response.json()['items']
    assert len(items) == 1
    assert items[0]['id'] == bonus.pk


@pytest.mark.django_db
def test_transactions_to_filter_includes_entries_late_on_the_to_day(client, registered_user, auth_headers):
    """The `to` filter is inclusive of the entire day, not just midnight."""
    bonus = registered_user.account.transactions.get()
    today = timezone.now().date()
    late_today = timezone.now().replace(hour=23, minute=59, second=59, microsecond=0)
    Transaction.objects.filter(pk=bonus.pk).update(timestamp=late_today)

    response = client.get('/api/accounts/transactions', {'to': today.isoformat()}, headers=auth_headers)

    assert response.status_code == 200
    items = response.json()['items']
    assert len(items) == 1
    assert items[0]['id'] == bonus.pk


@pytest.mark.django_db
def test_transactions_from_and_to_filter_together_select_only_the_in_range_entry(
    client,
    registered_user,
    auth_headers,
):
    """Combining `from` and `to` returns only the transaction that falls inside both bounds."""
    bonus = registered_user.account.transactions.get()
    Transaction.objects.filter(pk=bonus.pk).update(timestamp=timezone.now() - timedelta(days=30))
    before = Transaction.objects.create(
        account=registered_user.account,
        type=TransactionType.DEBIT,
        amount=Decimal('1.00'),
    )
    Transaction.objects.filter(pk=before.pk).update(timestamp=timezone.now() - timedelta(days=5))
    inside = Transaction.objects.create(
        account=registered_user.account,
        type=TransactionType.DEBIT,
        amount=Decimal('2.00'),
    )
    after = Transaction.objects.create(
        account=registered_user.account,
        type=TransactionType.DEBIT,
        amount=Decimal('3.00'),
    )
    Transaction.objects.filter(pk=after.pk).update(timestamp=timezone.now() + timedelta(days=5))

    params = {
        'from': (timezone.now() - timedelta(days=1)).date().isoformat(),
        'to': (timezone.now() + timedelta(days=1)).date().isoformat(),
    }
    response = client.get('/api/accounts/transactions', params, headers=auth_headers)

    items = response.json()['items']
    assert len(items) == 1
    assert items[0]['id'] == inside.pk


@pytest.mark.django_db
def test_transactions_are_ordered_newest_first(client, registered_user, auth_headers):
    """Transactions are returned newest first."""
    bonus = registered_user.account.transactions.get()
    newer = Transaction.objects.create(
        account=registered_user.account,
        type=TransactionType.DEBIT,
        amount=Decimal('1.00'),
    )
    Transaction.objects.filter(pk=newer.pk).update(timestamp=timezone.now() + timedelta(minutes=1))

    response = client.get('/api/accounts/transactions', headers=auth_headers)

    ids = [item['id'] for item in response.json()['items']]
    assert ids == [newer.pk, bonus.pk]


@pytest.mark.django_db
def test_transactions_excludes_other_users_transactions(client, registered_user, auth_headers):
    """A user's transaction history never includes another user's transactions."""
    other_user = register_user('other-history@example.com', 'a-strong-password-123')
    Transaction.objects.create(account=other_user.account, type=TransactionType.DEBIT, amount=Decimal('999.00'))

    response = client.get('/api/accounts/transactions', headers=auth_headers)

    assert response.status_code == 200
    items = response.json()['items']
    assert len(items) == 1
    assert items[0]['id'] == registered_user.account.transactions.get().pk


@pytest.mark.django_db
def test_transactions_are_paginated(client, registered_user, auth_headers):
    """The history endpoint returns one page of items plus the total count."""
    for _ in range(4):
        Transaction.objects.create(account=registered_user.account, type=TransactionType.DEBIT, amount=Decimal('1.00'))

    response = client.get('/api/accounts/transactions', {'page': 1, 'page_size': 2}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body['items']) == 2
    assert body['count'] == 5

    page_two = client.get('/api/accounts/transactions', {'page': 2, 'page_size': 2}, headers=auth_headers)
    page_two_items = page_two.json()['items']
    assert len(page_two_items) == 2
    assert {item['id'] for item in body['items']}.isdisjoint({item['id'] for item in page_two_items})


@pytest.fixture
def other_registered_user(db):
    """Register a second user to act as a transfer receiver."""
    return register_user('l@example.com', 'a-strong-password-123')


def test_transfer_requires_authentication(client):
    """The transfer endpoint returns 401 without a token."""
    response = client.post(
        '/api/accounts/transfer',
        {'account_number': '9999999999', 'amount': '10.00'},
        content_type='application/json',
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_transfer_success(client, registered_user, other_registered_user, auth_headers):
    """A valid transfer returns 201 with the amount, fee and total debited, and moves the money."""
    response = client.post(
        '/api/accounts/transfer',
        {'account_number': other_registered_user.account.account_number, 'amount': '1000.00'},
        content_type='application/json',
        headers=auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body['account_number'] == other_registered_user.account.account_number
    assert Decimal(body['amount']) == Decimal('1000.00')
    assert Decimal(body['fee']) == Decimal('25.00')
    assert Decimal(body['total_debited']) == Decimal('1025.00')

    balance_response = client.get('/api/accounts/balance', headers=auth_headers)
    assert Decimal(balance_response.json()['balance']) == Decimal('8975.00')

    other_refresh: RefreshToken = RefreshToken.for_user(other_registered_user)  # type: ignore[assignment,misc]
    other_headers = {'Authorization': f'Bearer {other_refresh.access_token}'}
    receiver_transactions = client.get('/api/accounts/transactions', headers=other_headers)
    receiver_items = receiver_transactions.json()['items']
    assert any(Decimal(item['amount']) == Decimal('1000.00') and item['type'] == 'credit' for item in receiver_items)


@pytest.mark.django_db
def test_transfer_to_unknown_account_returns_404(client, registered_user, auth_headers):
    """Transferring to a non-existent account number returns 404."""
    response = client.post(
        '/api/accounts/transfer',
        {'account_number': '9999999999', 'amount': '10.00'},
        content_type='application/json',
        headers=auth_headers,
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_transfer_insufficient_funds_returns_422(client, registered_user, other_registered_user, auth_headers):
    """Transferring more than the balance covers returns 422 with a fixed, generic detail message."""
    response = client.post(
        '/api/accounts/transfer',
        {'account_number': other_registered_user.account.account_number, 'amount': '50000.00'},
        content_type='application/json',
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.json()['detail'] == 'Insufficient funds'


@pytest.mark.django_db
def test_transfer_to_self_returns_422(client, registered_user, auth_headers):
    """Transferring to your own account number returns 422 with a fixed, generic detail message."""
    response = client.post(
        '/api/accounts/transfer',
        {'account_number': registered_user.account.account_number, 'amount': '10.00'},
        content_type='application/json',
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.json()['detail'] == 'Cannot transfer to your own account'


@pytest.mark.django_db
def test_transfer_with_non_positive_amount_returns_422(client, registered_user, other_registered_user, auth_headers):
    """A zero or negative amount is rejected by schema validation before any business logic runs."""
    response = client.post(
        '/api/accounts/transfer',
        {'account_number': other_registered_user.account.account_number, 'amount': '0.00'},
        content_type='application/json',
        headers=auth_headers,
    )

    assert response.status_code == 422


@pytest.mark.django_db
def test_transfer_records_a_debit_of_the_total_in_the_sender_history(
    client,
    registered_user,
    other_registered_user,
    auth_headers,
):
    """The sender's own history gains a debit entry for the amount plus the fee."""
    client.post(
        '/api/accounts/transfer',
        {'account_number': other_registered_user.account.account_number, 'amount': '1000.00'},
        content_type='application/json',
        headers=auth_headers,
    )

    items = client.get('/api/accounts/transactions', headers=auth_headers).json()['items']
    debits = [item for item in items if item['type'] == TransactionType.DEBIT]
    assert [Decimal(item['amount']) for item in debits] == [Decimal('1025.00')]


@pytest.mark.django_db
@pytest.mark.parametrize('amount', ['10.001', '99999999999999.00', '-10.00'])
def test_transfer_with_invalid_amount_returns_422(client, registered_user, other_registered_user, auth_headers, amount):
    """Over-precise, oversized and negative amounts are all rejected with 422."""
    response = client.post(
        '/api/accounts/transfer',
        {'account_number': other_registered_user.account.account_number, 'amount': amount},
        content_type='application/json',
        headers=auth_headers,
    )

    assert response.status_code == 422


@pytest.mark.django_db
def test_transfer_rejects_an_invalid_amount_that_bypasses_schema_validation(registered_user, other_registered_user):
    """An invalid amount reaching the service layer maps to 422 rather than a 500."""
    request = RequestFactory().post('/api/accounts/transfer')
    request.user = registered_user
    payload = TransferInScheme.model_construct(
        account_number=other_registered_user.account.account_number,
        amount=Decimal('10.001'),
    )

    status, body = transfer(request, payload)

    assert status == HTTPStatus.UNPROCESSABLE_ENTITY
    assert body == {'detail': 'Invalid transfer amount'}
