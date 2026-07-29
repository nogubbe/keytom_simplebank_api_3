"""HTTP endpoints for balance, transaction history and transfers."""

from http import HTTPStatus
from typing import cast

from django.contrib.auth.models import User
from django.http import HttpRequest
from ninja import Router
from ninja_jwt.authentication import JWTAuth

from .exceptions import AccountNotFoundError
from .models import Account
from .schemas import BalanceOutScheme, ErrorOutScheme
from .services import get_account

router = Router(tags=['accounts'], auth=JWTAuth())


def _current_user(request: HttpRequest) -> User:
    """Return the authenticated user attached to the request by JWTAuth."""
    return cast(User, request.user)


@router.get('/balance', response={HTTPStatus.OK: BalanceOutScheme, HTTPStatus.NOT_FOUND: ErrorOutScheme})
def balance(request: HttpRequest) -> tuple[HTTPStatus, dict[str, str] | Account]:
    """Return the authenticated user's account number and current balance."""
    try:
        account = get_account(_current_user(request))
    except AccountNotFoundError:
        return HTTPStatus.NOT_FOUND, {'detail': 'Account not found'}
    return HTTPStatus.OK, account
