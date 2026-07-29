"""Exceptions raised by the users app's services."""


class EmailAlreadyRegisteredError(Exception):
    """Raised when registering with an email that already has an account."""
