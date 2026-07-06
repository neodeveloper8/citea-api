from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        CLIENTE = "cliente", "Cliente"
        DUENO = "dueno", "Dueño"
        PLATFORM_ADMIN = "platform_admin", "Admin de plataforma"

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CLIENTE)
    email_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email

    @property
    def is_cliente(self):
        return self.role == self.Role.CLIENTE

    @property
    def is_dueno(self):
        return self.role == self.Role.DUENO

    @property
    def is_platform_admin(self):
        return self.role == self.Role.PLATFORM_ADMIN
