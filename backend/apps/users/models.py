from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_ANALYST = 'analyst'
    ROLE_ADMIN = 'admin'
    ROLE_CHOICES = [
        (ROLE_ANALYST, 'Analyst'),
        (ROLE_ADMIN, 'Admin'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_ANALYST)
    client = models.ForeignKey(
        'clients.Client', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='users'
    )

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_analyst(self):
        return self.role == self.ROLE_ANALYST
