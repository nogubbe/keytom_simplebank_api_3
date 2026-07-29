"""Exceptions raised by the users app's services."""


class EmailAlreadyRegisteredError(Exception):
    """Raised when registering with an email that already has an account."""


class WeakPasswordError(Exception):
    """Raised when a registration password fails Django's password validators."""

    def __init__(self, messages: list[str]) -> None:
        """Store the individual validator failure messages alongside the combined message."""
        self.messages = messages
        super().__init__('; '.join(messages))
