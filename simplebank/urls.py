"""URL configuration for simplebank project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""

from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest
from django.urls import path
from ninja import NinjaAPI

from simplebank.apps.accounts.api import router as accounts_router
from simplebank.apps.users.api import router as users_router

api = NinjaAPI(title='SimpleBank API', docs_url='/docs' if settings.DEBUG else None)

api.add_router('/auth', users_router)
api.add_router('/accounts', accounts_router)


@api.get('/health')
def health(request: HttpRequest) -> dict[str, str]:
    """Return a simple liveness check payload."""
    return {'status': 'ok'}


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api.urls),
]
