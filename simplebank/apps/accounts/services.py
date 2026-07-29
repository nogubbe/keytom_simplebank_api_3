"""Business logic for accounts, balances, transaction history and transfers."""

import secrets
import string
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from .enums import TransactionType
from .exceptions import AccountNotFoundError, AccountNumberGenerationError
from .models import Account, Transaction

WELCOME_BONUS = Decimal('10000.00')
MAX_ACCOUNT_NUMBER_ATTEMPTS = 5


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
