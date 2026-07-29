"""Business logic for accounts, balances, transaction history and transfers."""

import secrets
import string
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from .enums import TransactionType
from .exceptions import (
    AccountNotFoundError,
    AccountNumberGenerationError,
    InsufficientFundsError,
    InvalidTransferAmountError,
    SameAccountTransferError,
    SenderAccountNotFoundError,
)
from .models import Account, Transaction, Transfer

WELCOME_BONUS = Decimal('10000.00')
MAX_ACCOUNT_NUMBER_ATTEMPTS = 5
MIN_TRANSFER_FEE = Decimal('5.00')
TRANSFER_FEE_RATE = Decimal('0.025')
# Matches Account.balance / Transfer.amount's max_digits=12, decimal_places=2.
MAX_TRANSFER_AMOUNT = Decimal('9999999999.99')


def _generate_account_number() -> str:
    """Generate a random 10-digit account number string."""
    return ''.join(secrets.choice(string.digits) for _ in range(10))


def create_account_for_user(user: User) -> Account:
    """Create a bank account for a user, crediting the welcome bonus."""
    for _ in range(MAX_ACCOUNT_NUMBER_ATTEMPTS):
        try:
            with transaction.atomic():
                account = Account.objects.create(
                    user=user,
                    account_number=_generate_account_number(),
                    balance=WELCOME_BONUS,
                )
        except IntegrityError:
            continue
        else:
            Transaction.objects.create(account=account, type=TransactionType.CREDIT, amount=WELCOME_BONUS)
            return account
    raise AccountNumberGenerationError


def get_account(user: User) -> Account:
    """Return the authenticated user's account, or raise AccountNotFoundError if they have none."""
    try:
        return Account.objects.get(user=user)
    except Account.DoesNotExist as exc:
        raise AccountNotFoundError from exc


def list_transactions(account: Account, date_from: date | None, date_to: date | None) -> QuerySet[Transaction]:
    """Return an account's transactions, optionally filtered by date range."""
    transactions = Transaction.objects.filter(account=account).order_by('-timestamp', '-id')
    if date_from is not None:
        transactions = transactions.filter(timestamp__gte=_start_of_day(date_from))
    if date_to is not None:
        transactions = transactions.filter(timestamp__lt=_start_of_day(date_to + timedelta(days=1)))
    return transactions


def _start_of_day(day: date) -> datetime:
    """Return the given date's midnight as a timezone-aware datetime."""
    return timezone.make_aware(datetime.combine(day, time.min))


def calculate_fee(amount: Decimal) -> Decimal:
    """Return the greater of 2.5% of the amount or the €5 minimum fee, rounded to 2 decimals."""
    percentage_fee = (amount * TRANSFER_FEE_RATE).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return max(percentage_fee, MIN_TRANSFER_FEE)


# Both rows are locked by a single SELECT ... FOR UPDATE ... ORDER BY statement rather than
# two separate lock acquisitions. Both concurrent sessions execute the same query plan over
# the same two rows, so both traverse them in the same order regardless of which account each
# session calls "sender" — that shared traversal order is what rules out a lock-ordering cycle
# between opposing transfers (A->B and B->A). The ORDER BY keeps that order aligned with pk
# instead of leaving it to whatever the current plan happens to produce.
def _lock_transfer_accounts(sender_pk: int, receiver_pk: int) -> tuple[Account, Account]:
    """Lock and return the sender and receiver accounts in a deadlock-safe pk order."""
    locked = Account.objects.select_for_update().filter(pk__in=[sender_pk, receiver_pk]).order_by('pk')
    by_pk = {account.pk: account for account in locked}
    if sender_pk not in by_pk:
        raise SenderAccountNotFoundError
    if receiver_pk not in by_pk:
        raise AccountNotFoundError
    return by_pk[sender_pk], by_pk[receiver_pk]


def execute_transfer(sender: Account, receiver_account_number: str, amount: Decimal) -> Transfer:
    """Transfer money from sender to the account with receiver_account_number, applying the fee.

    The passed-in `sender` instance is not updated in place — its `.balance` still holds the
    pre-transfer value after this returns. Re-fetch the account if you need the new balance.
    """
    if amount <= 0 or amount > MAX_TRANSFER_AMOUNT or amount != amount.quantize(Decimal('0.01')):
        raise InvalidTransferAmountError
    try:
        receiver = Account.objects.get(account_number=receiver_account_number)
    except Account.DoesNotExist as exc:
        raise AccountNotFoundError from exc
    if receiver.pk == sender.pk:
        raise SameAccountTransferError

    with transaction.atomic():
        locked_sender, locked_receiver = _lock_transfer_accounts(sender.pk, receiver.pk)
        fee = calculate_fee(amount)
        total_debit = amount + fee
        if locked_sender.balance < total_debit:
            raise InsufficientFundsError

        transfer = Transfer.objects.create(
            sender_account=locked_sender,
            receiver_account=locked_receiver,
            amount=amount,
            fee=fee,
        )
        Transaction.objects.create(
            account=locked_sender,
            type=TransactionType.DEBIT,
            amount=amount,
            transfer=transfer,
        )
        Transaction.objects.create(
            account=locked_sender,
            type=TransactionType.DEBIT,
            amount=fee,
            transfer=transfer,
        )
        Transaction.objects.create(
            account=locked_receiver,
            type=TransactionType.CREDIT,
            amount=amount,
            transfer=transfer,
        )
        locked_sender.balance -= total_debit
        locked_receiver.balance += amount
        locked_sender.save(update_fields=['balance', 'updated_at'])
        locked_receiver.save(update_fields=['balance', 'updated_at'])
        return transfer
