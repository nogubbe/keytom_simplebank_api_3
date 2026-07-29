"""Django admin registrations for the accounts app."""

from django.contrib import admin

from .models import Account, Transaction, Transfer

admin.site.register(Account)
admin.site.register(Transfer)
admin.site.register(Transaction)
