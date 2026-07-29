"""HTTP endpoints for balance, transaction history and transfers."""

from datetime import date
from http import HTTPStatus
from typing import cast

from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.http import HttpRequest
from ninja import Query, Router
from ninja.errors import HttpError
from ninja.pagination import PageNumberPagination, paginate
from ninja_jwt.authentication import JWTAuth

from .exceptions import (
    AccountNotFoundError,
    InsufficientFundsError,
    InvalidTransferAmountError,
    SameAccountTransferError,
)
from .models import Account, Transaction
from .schemas import BalanceOutScheme, ErrorOutScheme, TransactionOutScheme, TransferInScheme, TransferOutScheme
from .services import execute_transfer, get_account, list_transactions

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


@router.get('/transactions', response=list[TransactionOutScheme])
@paginate(PageNumberPagination)
def transactions(
    request: HttpRequest,
    date_from: date | None = Query(None, alias='from'),  # noqa: B008
    date_to: date | None = Query(None, alias='to'),  # noqa: B008
) -> QuerySet[Transaction]:
    """Return the authenticated user's transaction history, newest first."""
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HttpError(HTTPStatus.UNPROCESSABLE_ENTITY, '`from` date must not be after `to` date')
    try:
        account = get_account(_current_user(request))
    except AccountNotFoundError as exc:
        raise HttpError(HTTPStatus.NOT_FOUND, 'Account not found') from exc
    return list_transactions(account, date_from, date_to)


@router.post(
    '/transfer',
    response={
        HTTPStatus.CREATED: TransferOutScheme,
        HTTPStatus.NOT_FOUND: ErrorOutScheme,
        HTTPStatus.UNPROCESSABLE_ENTITY: ErrorOutScheme,
    },
)
def transfer(request: HttpRequest, payload: TransferInScheme) -> tuple[HTTPStatus, dict[str, str] | TransferOutScheme]:
    """Transfer money from the authenticated user's account to another account."""
    try:
        sender = get_account(_current_user(request))
    except AccountNotFoundError:
        return HTTPStatus.NOT_FOUND, {'detail': 'Your account was not found'}
    try:
        result = execute_transfer(sender, payload.account_number, payload.amount)
    except AccountNotFoundError:
        return HTTPStatus.NOT_FOUND, {'detail': 'Recipient account not found'}
    except SameAccountTransferError:
        return HTTPStatus.UNPROCESSABLE_ENTITY, {'detail': 'Cannot transfer to your own account'}
    except InsufficientFundsError:
        return HTTPStatus.UNPROCESSABLE_ENTITY, {'detail': 'Insufficient funds'}
    except InvalidTransferAmountError:
        return HTTPStatus.UNPROCESSABLE_ENTITY, {'detail': 'Invalid transfer amount'}
    return HTTPStatus.CREATED, TransferOutScheme(
        account_number=payload.account_number,
        amount=result.amount,
        fee=result.fee,
        total_debited=result.total_debited,
    )
