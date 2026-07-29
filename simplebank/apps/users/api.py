"""HTTP endpoints for user registration and login."""

from http import HTTPStatus
from typing import Any

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.http import HttpRequest
from ninja import Router
from ninja_jwt.tokens import RefreshToken

from simplebank.apps.accounts.exceptions import AccountNumberGenerationError

from .exceptions import EmailAlreadyRegisteredError
from .schemas import ErrorOutScheme, LoginInScheme, RegisterInScheme, RegisterOutScheme, TokenOutScheme
from .services import register_user

router = Router(tags=['auth'])


@router.post(
    '/register',
    response={
        HTTPStatus.CREATED: RegisterOutScheme,
        HTTPStatus.CONFLICT: ErrorOutScheme,
        HTTPStatus.UNPROCESSABLE_ENTITY: ErrorOutScheme,
        HTTPStatus.SERVICE_UNAVAILABLE: ErrorOutScheme,
    },
)
def register(request: HttpRequest, payload: RegisterInScheme) -> tuple[HTTPStatus, dict[str, str] | User]:
    """Register a new user."""
    try:
        user = register_user(payload.email, payload.password)
    except EmailAlreadyRegisteredError:
        return HTTPStatus.CONFLICT, {'detail': 'Email is already registered'}
    except ValueError as exc:
        return HTTPStatus.UNPROCESSABLE_ENTITY, {'detail': str(exc)}
    except AccountNumberGenerationError:
        return HTTPStatus.SERVICE_UNAVAILABLE, {'detail': 'Could not create an account, please try again'}
    return HTTPStatus.CREATED, user


@router.post('/login', response={HTTPStatus.OK: TokenOutScheme, HTTPStatus.UNAUTHORIZED: ErrorOutScheme})
def login(request: HttpRequest, payload: LoginInScheme) -> tuple[int, Any]:
    """Authenticate a user and return a JWT access/refresh token pair."""
    user = authenticate(request, username=payload.email.lower(), password=payload.password)
    if user is None:
        return HTTPStatus.UNAUTHORIZED, {'detail': 'Invalid credentials'}
    # ninja_jwt.tokens.RefreshToken.for_user is typed as `cls: T` instead of `cls: type[T]`,
    # tripping mypy on a correct call — workaround for that upstream typing bug.
    refresh: RefreshToken = RefreshToken.for_user(user)  # type: ignore[assignment,misc]
    return HTTPStatus.OK, {'access': str(refresh.access_token), 'refresh': str(refresh)}
