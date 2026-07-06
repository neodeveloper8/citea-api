# Create your tests here.
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status

User = get_user_model()


# ---------- Tests del modelo / manager ----------


@pytest.mark.django_db
class TestUserModel:
    def test_create_user_default_role_is_cliente(self):
        """Un usuario creado sin rol explícito debe ser 'cliente'."""
        user = User.objects.create_user(email="a@test.pe", password="ClaveTest123")
        assert user.role == User.Role.CLIENTE
        assert user.is_cliente is True

    def test_create_user_hashes_password(self):
        """El password NUNCA debe guardarse en texto plano."""
        user = User.objects.create_user(email="b@test.pe", password="ClaveTest123")
        assert user.password != "ClaveTest123"  # está hasheado, no es el texto literal
        assert user.check_password("ClaveTest123") is True  # pero valida correctamente

    def test_create_user_without_email_fails(self):
        """Sin email debe reventar (es el identificador)."""
        with pytest.raises(ValueError):
            User.objects.create_user(email="", password="ClaveTest123")

    def test_create_superuser_is_platform_admin(self):
        """El superuser debe tener rol platform_admin y los flags correctos."""
        admin = User.objects.create_superuser(
            email="admin@test.pe", password="ClaveTest123"
        )
        assert admin.is_platform_admin is True
        assert admin.is_staff is True
        assert admin.is_superuser is True
        assert admin.email_verified is True


# ---------- Tests de registro ----------


@pytest.mark.django_db
class TestRegister:
    def test_register_success(self, api_client):
        """Registro válido crea usuario y devuelve tokens."""
        response = api_client.post(
            reverse("register"),
            {
                "email": "nuevo@test.pe",
                "password": "ClaveSegura123",
                "phone": "987654321",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert "tokens" in response.data
        assert response.data["user"]["email"] == "nuevo@test.pe"

    def test_register_cannot_set_role(self, api_client):
        """🔑 SEGURIDAD: un usuario NO puede auto-asignarse un rol.
        Aunque mande role=platform_admin, debe quedar como cliente."""
        response = api_client.post(
            reverse("register"),
            {
                "email": "hacker@test.pe",
                "password": "ClaveSegura123",
                "role": "platform_admin",  # intento de escalación
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        user = User.objects.get(email="hacker@test.pe")
        assert user.role == User.Role.CLIENTE  # NO se convirtió en admin

    def test_register_weak_password_rejected(self, api_client):
        """Password débil debe rechazarse con el formato de error estándar."""
        response = api_client.post(
            reverse("register"),
            {
                "email": "debil@test.pe",
                "password": "123",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "validation_error"
        assert "password" in response.data["details"]

    def test_register_duplicate_email_rejected(self, api_client, cliente_user):
        """No se puede registrar dos veces el mismo email."""
        response = api_client.post(
            reverse("register"),
            {
                "email": "cliente@test.pe",  # ya existe (viene de la fixture)
                "password": "ClaveSegura123",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------- Tests de login ----------


@pytest.mark.django_db
class TestLogin:
    def test_login_success(self, api_client, cliente_user):
        """Login con credenciales correctas devuelve tokens."""
        response = api_client.post(
            reverse("login"),
            {
                "email": "cliente@test.pe",
                "password": "ClaveTest123",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data["tokens"]

    def test_login_wrong_password_generic_message(self, api_client, cliente_user):
        """🔑 SEGURIDAD: password incorrecto da mensaje genérico (no revela detalles)."""
        response = api_client.post(
            reverse("login"),
            {
                "email": "cliente@test.pe",
                "password": "ClaveIncorrecta",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data["code"] == "authentication_failed"

    def test_login_nonexistent_email_generic_message(self, api_client):
        """🔑 SEGURIDAD: email inexistente da el MISMO mensaje (anti-enumeración)."""
        response = api_client.post(
            reverse("login"),
            {
                "email": "noexiste@test.pe",
                "password": "ClaveTest123",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data["code"] == "authentication_failed"


# ---------- Tests de password-reset ----------


@pytest.mark.django_db
class TestPasswordReset:
    def test_reset_request_always_same_response(self, api_client):
        """🔑 SEGURIDAD: la respuesta es idéntica exista o no el email."""
        response = api_client.post(
            reverse("password_reset"),
            {
                "email": "noexiste@test.pe",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

    def test_reset_confirm_changes_password(self, api_client, cliente_user):
        """El flujo completo de reset cambia el password."""
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        uid = urlsafe_base64_encode(force_bytes(cliente_user.pk))
        token = default_token_generator.make_token(cliente_user)

        response = api_client.post(
            reverse("password_reset_confirm"),
            {
                "uid": uid,
                "token": token,
                "new_password": "PasswordNuevo456",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        cliente_user.refresh_from_db()
        assert cliente_user.check_password("PasswordNuevo456") is True


# ---------- Tests de email-verify ----------


@pytest.mark.django_db
class TestEmailVerify:
    def test_verify_marks_email_verified(self, api_client, cliente_user):
        """Verificar con token válido marca email_verified=True."""
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        assert cliente_user.email_verified is False  # arranca sin verificar

        uid = urlsafe_base64_encode(force_bytes(cliente_user.pk))
        token = default_token_generator.make_token(cliente_user)

        response = api_client.post(
            reverse("verify_email"),
            {
                "uid": uid,
                "token": token,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        cliente_user.refresh_from_db()
        assert cliente_user.email_verified is True
