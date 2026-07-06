import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def api_client():
    """Cliente HTTP para hacer requests a la API en los tests."""
    return APIClient()


@pytest.fixture
def cliente_user(db):
    """Un usuario con rol cliente, ya creado en la BD de test.
    El parámetro 'db' es una fixture de pytest-django que da acceso a la BD."""
    return User.objects.create_user(
        email="cliente@test.pe",
        password="ClaveTest123",
        phone="987654321",
    )


@pytest.fixture
def dueno_user(db):
    """Un usuario con rol dueño."""
    return User.objects.create_user(
        email="dueno@test.pe",
        password="ClaveTest123",
        role=User.Role.DUENO,
    )
