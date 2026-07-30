"""Database models for the accounts app: accounts, transfers and transactions."""

from decimal import Decimal
from typing import ClassVar

from django.contrib.auth.models import User
from django.core.validators import MinLengthValidator
from django.db import models

from .enums import TransactionType


class Account(models.Model):
    """A user's single bank account holding a EUR balance."""

    user = models.OneToOneField(User, on_delete=models.PROTECT, related_name='account')
    account_number = models.CharField(max_length=10, unique=True, validators=[MinLengthValidator(10)])
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Enforce at the database level that a balance can never go negative."""

        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(condition=models.Q(balance__gte=0), name='account_balance_non_negative'),
        ]

    def __str__(self) -> str:
        """Return the account number for display in admin and shells."""
        return self.account_number


class Transfer(models.Model):
    """A single transfer operation between two accounts."""

    sender_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='outgoing_transfers')
    receiver_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='incoming_transfers')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    fee = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Enforce at the database level that transfer amounts and fees are positive."""

        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='transfer_amount_positive'),
            models.CheckConstraint(condition=models.Q(fee__gte=0), name='transfer_fee_non_negative'),
        ]

    def __str__(self) -> str:
        """Return a short human-readable summary of the transfer."""
        return f'{self.sender_account} -> {self.receiver_account}: {self.amount}'

    @property
    def total_debited(self) -> Decimal:
        """Return the total amount debited from the sender: amount plus fee."""
        return self.amount + self.fee


class Transaction(models.Model):
    """A single ledger entry (credit or debit) against one account."""

    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='transactions')
    type = models.CharField(max_length=6, choices=[(t.value, t.name.capitalize()) for t in TransactionType])
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    timestamp = models.DateTimeField(auto_now_add=True)
    transfer = models.ForeignKey(
        Transfer,
        on_delete=models.PROTECT,
        related_name='transactions',
        null=True,
        blank=True,
    )

    class Meta:
        """Index transactions by account and timestamp, and require a positive amount."""

        indexes: ClassVar[list[models.Index]] = [models.Index(fields=['account', 'timestamp'])]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='transaction_amount_positive'),
        ]

    def __str__(self) -> str:
        """Return a short human-readable summary of the transaction."""
        return f'{self.account}: {self.type} {self.amount}'
