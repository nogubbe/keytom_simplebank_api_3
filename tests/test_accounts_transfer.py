"""Tests for the execute_transfer service: balances, ledger entries, atomicity and locking."""

import threading
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext

from simplebank.apps.accounts.enums import TransactionType
from simplebank.apps.accounts.exceptions import (
    AccountNotFoundError,
    InsufficientFundsError,
    InvalidTransferAmountError,
    SameAccountTransferError,
    SenderAccountNotFoundError,
)
from simplebank.apps.accounts.models import Account, Transaction, Transfer
from simplebank.apps.accounts.services import MAX_TRANSFER_AMOUNT, execute_transfer


def make_account(username: str, account_number: str, balance: str) -> Account:
    """Create a user with an account holding the given balance."""
    user = User.objects.create_user(username=username, email=username)
    return Account.objects.create(user=user, account_number=account_number, balance=Decimal(balance))


@pytest.fixture
def sender() -> Account:
    """Return a sender account holding €1000.00."""
    return make_account('sender@example.com', '1000000001', '1000.00')


@pytest.fixture
def receiver() -> Account:
    """Return a receiver account holding €0.00."""
    return make_account('receiver@example.com', '1000000002', '0.00')


@pytest.mark.django_db
def test_execute_transfer_debits_sender_by_amount_plus_fee(sender, receiver):
    """The sender's balance drops by the amount plus the fee."""
    execute_transfer(sender, receiver.account_number, Decimal('600.00'))

    sender.refresh_from_db()
    assert sender.balance == Decimal('385.00')


@pytest.mark.django_db
def test_execute_transfer_credits_receiver_by_amount_only(sender, receiver):
    """The receiver's balance rises by the amount, without the fee."""
    execute_transfer(sender, receiver.account_number, Decimal('600.00'))

    receiver.refresh_from_db()
    assert receiver.balance == Decimal('600.00')


@pytest.mark.django_db
def test_execute_transfer_returns_transfer_with_amount_and_fee(sender, receiver):
    """The returned Transfer records the amount, the fee and both accounts."""
    transfer = execute_transfer(sender, receiver.account_number, Decimal('600.00'))

    assert Transfer.objects.count() == 1
    assert transfer.amount == Decimal('600.00')
    assert transfer.fee == Decimal('15.00')
    assert transfer.total_debited == Decimal('615.00')
    assert transfer.sender_account_id == sender.pk
    assert transfer.receiver_account_id == receiver.pk


@pytest.mark.django_db
def test_execute_transfer_records_debit_and_credit_transactions(sender, receiver):
    """Exactly two ledger entries are written, both linked to the transfer."""
    transfer = execute_transfer(sender, receiver.account_number, Decimal('600.00'))

    assert Transaction.objects.count() == 2
    debit = Transaction.objects.get(account=sender)
    credit = Transaction.objects.get(account=receiver)
    assert debit.type == TransactionType.DEBIT
    assert debit.amount == Decimal('615.00')
    assert debit.transfer_id == transfer.pk
    assert credit.type == TransactionType.CREDIT
    assert credit.amount == Decimal('600.00')
    assert credit.transfer_id == transfer.pk


@pytest.mark.django_db
def test_execute_transfer_raises_on_insufficient_funds(sender, receiver):
    """A transfer whose amount plus fee exceeds the balance is rejected."""
    with pytest.raises(InsufficientFundsError):
        execute_transfer(sender, receiver.account_number, Decimal('990.00'))


@pytest.mark.django_db
def test_execute_transfer_writes_nothing_on_insufficient_funds(sender, receiver):
    """A rejected transfer leaves both balances and the ledger untouched."""
    with pytest.raises(InsufficientFundsError):
        execute_transfer(sender, receiver.account_number, Decimal('990.00'))

    sender.refresh_from_db()
    receiver.refresh_from_db()
    assert sender.balance == Decimal('1000.00')
    assert receiver.balance == Decimal('0.00')
    assert Transfer.objects.count() == 0
    assert Transaction.objects.count() == 0


@pytest.mark.django_db
def test_execute_transfer_rejects_transfer_to_own_account(sender):
    """Transferring to one's own account number is rejected."""
    with pytest.raises(SameAccountTransferError):
        execute_transfer(sender, sender.account_number, Decimal('100.00'))


@pytest.mark.django_db
def test_execute_transfer_rejects_unknown_receiver_account_number(sender):
    """An account number that does not exist is rejected."""
    with pytest.raises(AccountNotFoundError):
        execute_transfer(sender, '9999999999', Decimal('100.00'))


@pytest.mark.django_db
def test_execute_transfer_raises_sender_not_found_when_sender_row_is_gone(receiver):
    """If the sender's own account row no longer exists, the sender-specific error is raised."""
    deleted_user = User.objects.create_user(username='ghost@example.com', email='ghost@example.com')
    ghost_sender = Account.objects.create(user=deleted_user, account_number='1000000099', balance=Decimal('1000.00'))
    ghost_sender_pk = ghost_sender.pk
    Account.objects.filter(pk=ghost_sender_pk).delete()
    ghost_sender.pk = ghost_sender_pk

    with pytest.raises(SenderAccountNotFoundError):
        execute_transfer(ghost_sender, receiver.account_number, Decimal('10.00'))


@pytest.mark.django_db
def test_execute_transfer_rejects_negative_amount(sender, receiver):
    """A negative amount is rejected instead of crediting the sender and draining the receiver."""
    with pytest.raises(InvalidTransferAmountError):
        execute_transfer(sender, receiver.account_number, Decimal('-100.00'))

    sender.refresh_from_db()
    receiver.refresh_from_db()
    assert sender.balance == Decimal('1000.00')
    assert receiver.balance == Decimal('0.00')


@pytest.mark.django_db
def test_execute_transfer_rejects_zero_amount(sender, receiver):
    """A zero amount is rejected."""
    with pytest.raises(InvalidTransferAmountError):
        execute_transfer(sender, receiver.account_number, Decimal('0.00'))


@pytest.mark.django_db
def test_execute_transfer_rejects_amount_over_the_max_digits_the_model_can_store(sender, receiver):
    """An amount larger than max_digits=12 can represent is rejected instead of hitting a DB error."""
    with pytest.raises(InvalidTransferAmountError):
        execute_transfer(sender, receiver.account_number, MAX_TRANSFER_AMOUNT + Decimal('0.01'))

    sender.refresh_from_db()
    receiver.refresh_from_db()
    assert sender.balance == Decimal('1000.00')
    assert receiver.balance == Decimal('0.00')


@pytest.mark.django_db
def test_execute_transfer_rejects_amount_with_more_than_two_decimal_places(sender, receiver):
    """An amount with sub-cent precision is rejected instead of desynchronizing balance and ledger."""
    with pytest.raises(InvalidTransferAmountError):
        execute_transfer(sender, receiver.account_number, Decimal('100.005'))

    sender.refresh_from_db()
    receiver.refresh_from_db()
    assert sender.balance == Decimal('1000.00')
    assert receiver.balance == Decimal('0.00')


@pytest.mark.django_db
def test_execute_transfer_applies_the_minimum_fee_end_to_end(sender, receiver):
    """Below the 2.5%-vs-€5 crossover, the €5 minimum fee is what actually gets debited and ledgered."""
    transfer = execute_transfer(sender, receiver.account_number, Decimal('100.00'))

    sender.refresh_from_db()
    receiver.refresh_from_db()
    assert transfer.fee == Decimal('5.00')
    assert sender.balance == Decimal('895.00')
    assert receiver.balance == Decimal('100.00')
    debit = Transaction.objects.get(account=sender)
    assert debit.amount == Decimal('105.00')


@pytest.mark.django_db
def test_execute_transfer_can_drain_sender_balance_to_exactly_zero(sender, receiver):
    """A transfer whose amount plus fee exactly equals the balance succeeds, leaving zero."""
    execute_transfer(sender, receiver.account_number, Decimal('975.61'))

    sender.refresh_from_db()
    assert sender.balance == Decimal('0.00')


@pytest.mark.django_db
def test_execute_transfer_to_self_wins_over_insufficient_funds(sender):
    """Self-transfer is rejected even when the amount would also fail an insufficient-funds check."""
    with pytest.raises(SameAccountTransferError):
        execute_transfer(sender, sender.account_number, Decimal('50000.00'))


class InjectedFailureError(Exception):
    """Stand-in for an unexpected error striking mid-transfer."""


@pytest.mark.django_db
def test_execute_transfer_rolls_back_everything_on_mid_transfer_failure(sender, receiver):
    """A failure after the sender's balance has already been written leaves no partial state behind."""
    real_save = Account.save
    calls: list[int] = []

    def failing_save(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise InjectedFailureError
        return real_save(self, *args, **kwargs)

    with patch.object(Account, 'save', failing_save), pytest.raises(InjectedFailureError):
        execute_transfer(sender, receiver.account_number, Decimal('600.00'))

    sender.refresh_from_db()
    receiver.refresh_from_db()
    assert sender.balance == Decimal('1000.00')
    assert receiver.balance == Decimal('0.00')
    assert Transfer.objects.count() == 0
    assert Transaction.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_transfers_cannot_overdraw_the_sender():
    """Two overlapping transfers that together would overdraw the sender: only one succeeds."""
    sender_account = make_account('c-sender@example.com', '2000000001', '1000.00')
    first_receiver = make_account('c-first@example.com', '2000000002', '0.00')
    second_receiver = make_account('c-second@example.com', '2000000003', '0.00')

    barrier = threading.Barrier(2)
    results: list[BaseException | None] = []
    lock = threading.Lock()

    def run(receiver_number: str) -> None:
        try:
            barrier.wait(timeout=10)
            execute_transfer(sender_account, receiver_number, Decimal('600.00'))
            outcome: BaseException | None = None
        except BaseException as exc:
            outcome = exc
        with lock:
            results.append(outcome)
        connection.close()

    threads = [
        threading.Thread(target=run, args=(first_receiver.account_number,)),
        threading.Thread(target=run, args=(second_receiver.account_number,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads)

    assert len(results) == 2
    successes = [r for r in results if r is None]
    failures = [r for r in results if isinstance(r, InsufficientFundsError)]
    assert len(successes) == 1, f'unexpected outcomes: {results}'
    assert len(failures) == 1, f'unexpected outcomes: {results}'

    sender_account.refresh_from_db()
    assert sender_account.balance == Decimal('385.00')
    assert Transfer.objects.count() == 1
    assert Transaction.objects.filter(transfer__isnull=False).count() == 2


@pytest.mark.django_db
def test_execute_transfer_locks_both_accounts_in_a_single_ordered_query(sender, receiver):
    """Both accounts are locked by one query, ordered by pk — not two separate lock acquisitions.

    Both concurrent callers execute this same query over the same two rows, so both traverse them
    in the same order regardless of which account each one calls "sender" — that shared traversal
    order is what rules out a lock-ordering cycle between opposing transfers. This asserts on the
    emitted SQL (a real, structural guard) rather than on the Python source text, which a refactor
    could preserve as a substring while changing the actual query shape.
    """
    with CaptureQueriesContext(connection) as ctx:
        execute_transfer(sender, receiver.account_number, Decimal('100.00'))

    lock_queries = [query['sql'] for query in ctx.captured_queries if 'FOR UPDATE' in query['sql']]
    assert len(lock_queries) == 1
    assert 'ORDER BY' in lock_queries[0]


@pytest.mark.django_db(transaction=True)
def test_opposing_concurrent_transfers_do_not_deadlock():
    """Simultaneous A->B and B->A transfers both complete instead of deadlocking.

    This is a best-effort integration check: the barrier only synchronizes thread start, so one
    transfer may fully commit before the other begins and the interleaving that could deadlock
    might not occur on a given run. The deterministic guard for the locking invariant itself is
    test_execute_transfer_locks_both_accounts_in_a_single_ordered_query, above.
    """
    account_a = make_account('d-a@example.com', '3000000001', '1000.00')
    account_b = make_account('d-b@example.com', '3000000002', '1000.00')

    barrier = threading.Barrier(2)
    results: list[BaseException | None] = []
    lock = threading.Lock()

    def run(sender_account: Account, receiver_number: str) -> None:
        try:
            barrier.wait(timeout=10)
            execute_transfer(sender_account, receiver_number, Decimal('100.00'))
            outcome: BaseException | None = None
        except BaseException as exc:
            outcome = exc
        with lock:
            results.append(outcome)
        connection.close()

    threads = [
        threading.Thread(target=run, args=(account_a, account_b.account_number)),
        threading.Thread(target=run, args=(account_b, account_a.account_number)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads)

    assert results == [None, None], f'unexpected outcomes: {results}'
    account_a.refresh_from_db()
    account_b.refresh_from_db()
    assert account_a.balance == Decimal('995.00')
    assert account_b.balance == Decimal('995.00')
