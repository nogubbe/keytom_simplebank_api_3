"""Exceptions raised by the accounts app's services."""


class AccountNumberGenerationError(Exception):
    """Raised when no unique account number could be generated after several attempts."""


class AccountNotFoundError(Exception):
    """Raised when a referenced account number does not exist."""


class InsufficientFundsError(Exception):
    """Raised when an account's balance cannot cover a transfer plus its fee."""


class SameAccountTransferError(Exception):
    """Raised when a transfer's sender and receiver account are the same."""


class InvalidTransferAmountError(Exception):
    """Raised when a transfer amount is zero, negative, or has more than 2 decimal places."""
