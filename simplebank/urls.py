"""
URL configuration for simplebank project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""

from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI

api = NinjaAPI(title='SimpleBank API')


@api.get('/health')
def health(request):
    return {'status': 'ok'}


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api.urls),
]
