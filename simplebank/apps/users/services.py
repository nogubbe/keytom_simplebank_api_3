"""Business logic for creating and authenticating users."""

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from simplebank.apps.accounts.services import create_account_for_user

from .exceptions import EmailAlreadyRegisteredError


def register_user(email: str, password: str) -> User:
    """Create a new user with the given email and password, lowercasing the email."""
    email = email.lower()
    if User.objects.filter(email=email).exists():
        raise EmailAlreadyRegisteredError(email)

    user = User(username=email, email=email)
    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise ValueError('; '.join(exc.messages)) from exc

    with transaction.atomic():
        user.set_password(password)
        user.save()
        create_account_for_user(user)
    return user
