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
from .exceptions import AccountNotFoundError, AccountNumberGenerationError
from .models import Account, Transaction

WELCOME_BONUS = Decimal('10000.00')
MAX_ACCOUNT_NUMBER_ATTEMPTS = 5
MIN_TRANSFER_FEE = Decimal('5.00')
TRANSFER_FEE_RATE = Decimal('0.025')


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


def list_transactions(user: User, date_from: date | None, date_to: date | None) -> QuerySet[Transaction]:
    """Return the authenticated user's transactions, optionally filtered by date range."""
    transactions = Transaction.objects.filter(account__user=user).order_by('-timestamp', '-id')
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
