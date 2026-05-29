from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'role', 'client', 'is_active']
    fieldsets = UserAdmin.fieldsets + (('ESG', {'fields': ('role', 'client')}),)
