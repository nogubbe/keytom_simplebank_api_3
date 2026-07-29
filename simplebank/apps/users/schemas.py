"""Request/response schemas for the users API."""

from ninja import Schema
from pydantic import EmailStr


class RegisterInScheme(Schema):
    """Request body for registering a new user."""

    email: EmailStr
    password: str


class RegisterOutScheme(Schema):
    """Response body for a successfully registered user."""

    id: int
    email: str


class LoginInScheme(Schema):
    """Request body for logging in."""

    email: EmailStr
    password: str


class TokenOutScheme(Schema):
    """Response body containing JWT access/refresh tokens."""

    access: str
    refresh: str


class ErrorOutScheme(Schema):
    """Generic error response body."""

    detail: str
