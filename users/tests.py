# Create your tests here.
from unittest.mock import patch

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

    def test_create_user_con_full_name_persiste(self):
        """create_user con full_name lo guarda tal cual, y persiste (refetch)."""
        User.objects.create_user(
            email="c@test.pe", password="ClaveTest123", full_name="Juan Pérez"
        )
        user = User.objects.get(email="c@test.pe")
        assert user.full_name == "Juan Pérez"

    def test_create_user_sin_full_name_default_es_string_vacio(self):
        """Sin full_name, el default es "" (string vacío), NO None."""
        user = User.objects.create_user(email="d@test.pe", password="ClaveTest123")
        assert user.full_name == ""
        assert user.full_name is not None

    def test_get_full_name_devuelve_full_name(self):
        user = User.objects.create_user(
            email="e@test.pe", password="ClaveTest123", full_name="Juan Pérez"
        )
        assert user.get_full_name() == "Juan Pérez"

    def test_get_short_name_devuelve_primer_token(self):
        user = User.objects.create_user(
            email="f@test.pe", password="ClaveTest123", full_name="Juan Pérez"
        )
        assert user.get_short_name() == "Juan"

    def test_get_short_name_vacio_si_full_name_vacio(self):
        user = User.objects.create_user(email="g@test.pe", password="ClaveTest123")
        assert user.get_short_name() == ""


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
                "full_name": "Juan Pérez",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert "tokens" in response.data
        assert response.data["user"]["email"] == "nuevo@test.pe"
        user = User.objects.get(email="nuevo@test.pe")
        assert user.full_name == "Juan Pérez"

    def test_register_cannot_set_role(self, api_client):
        """🔑 SEGURIDAD: un usuario NO puede auto-asignarse un rol.
        Aunque mande role=platform_admin, debe quedar como cliente."""
        response = api_client.post(
            reverse("register"),
            {
                "email": "hacker@test.pe",
                "password": "ClaveSegura123",
                "full_name": "Ana Torres",
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
                "full_name": "Test User",
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
                "full_name": "Test User",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_sin_full_name_rechazado(self, api_client):
        """full_name es obligatorio: sin mandarlo, 400 con el campo en el error."""
        response = api_client.post(
            reverse("register"),
            {
                "email": "sinnombre@test.pe",
                "password": "ClaveSegura123",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "full_name" in response.data["details"]

    def test_register_full_name_solo_espacios_rechazado(self, api_client):
        """trim_whitespace colapsa "  " a "" -> cae por required/min_length."""
        response = api_client.post(
            reverse("register"),
            {
                "email": "espacios@test.pe",
                "password": "ClaveSegura123",
                "full_name": "   ",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "full_name" in response.data["details"]

    def test_register_mail_caido_no_voltea_el_registro(self, api_client):
        """🔑 Un mail caído no debe impedir que el registro se complete."""
        with patch("core.emails.send_mail", side_effect=Exception("SMTP caído")):
            response = api_client.post(
                reverse("register"),
                {
                    "email": "mailcaido@test.pe",
                    "password": "ClaveSegura123",
                    "full_name": "Test User",
                },
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        assert User.objects.filter(email="mailcaido@test.pe").exists()


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

    def test_reset_request_email_registrado_con_mail_caido_misma_respuesta(
        self, api_client, cliente_user
    ):
        """🔑 SEGURIDAD: si el mail falla al enviarse para un email SÍ
        registrado, la respuesta sigue siendo idéntica a la de un email
        inexistente. Un mail caído no debe crear un oráculo de enumeración."""
        with patch("core.emails.send_mail", side_effect=Exception("SMTP caído")):
            response_registrado = api_client.post(
                reverse("password_reset"),
                {"email": "cliente@test.pe"},  # existe, viene de la fixture
                format="json",
            )

        response_inexistente = api_client.post(
            reverse("password_reset"),
            {"email": "noexiste@test.pe"},
            format="json",
        )

        assert response_registrado.status_code == response_inexistente.status_code
        assert response_registrado.data == response_inexistente.data

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
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        from users.tokens import email_verification_token

        assert cliente_user.email_verified is False  # arranca sin verificar

        uid = urlsafe_base64_encode(force_bytes(cliente_user.pk))
        # Generador propio de verify, no el de password-reset (ver users/tokens.py).
        token = email_verification_token.make_token(cliente_user)

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


# ---------- Los dos tokens no son intercambiables ----------


def _uid(user):
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    return urlsafe_base64_encode(force_bytes(user.pk))


@pytest.mark.django_db
class TestTokensNoIntercambiables:
    """verify y reset tienen que usar generadores DISTINTOS.

    Con un solo generador, un token emitido para confirmar un email sirve para
    cambiar la contraseña: quien intercepte un mail de bienvenida (o un link
    reenviado por el propio usuario) se queda con la cuenta.
    """

    def test_token_de_verify_no_sirve_para_resetear_password(
        self, api_client, cliente_user
    ):
        # ATAQUE. El token del mail de verificación se manda al endpoint de
        # reset. Tiene que ser rechazado y la contraseña quedar intacta.
        from users.tokens import email_verification_token

        token_verify = email_verification_token.make_token(cliente_user)

        response = api_client.post(
            reverse("password_reset_confirm"),
            {
                "uid": _uid(cliente_user),
                "token": token_verify,
                "new_password": "PasswordRobado789",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "validation_error"
        assert "token" in response.data["details"]
        cliente_user.refresh_from_db()
        # Se verifica en la BD: un 400 no probaría por sí solo que no cambió.
        assert cliente_user.check_password("PasswordRobado789") is False
        assert cliente_user.check_password("ClaveTest123") is True

    def test_token_de_reset_no_sirve_para_verificar_email(
        self, api_client, cliente_user
    ):
        from django.contrib.auth.tokens import default_token_generator

        token_reset = default_token_generator.make_token(cliente_user)

        response = api_client.post(
            reverse("verify_email"),
            {"uid": _uid(cliente_user), "token": token_reset},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        cliente_user.refresh_from_db()
        assert cliente_user.email_verified is False

    def test_token_de_verify_es_de_un_solo_uso(self, api_client, cliente_user):
        from users.tokens import email_verification_token

        token = email_verification_token.make_token(cliente_user)
        url = reverse("verify_email")
        payload = {"uid": _uid(cliente_user), "token": token}

        primera = api_client.post(url, payload, format="json")
        assert primera.status_code == status.HTTP_200_OK

        segunda = api_client.post(url, payload, format="json")

        # email_verified entra al hash: al pasar a True el token muere.
        assert segunda.status_code == status.HTTP_400_BAD_REQUEST

    def test_verify_sigue_funcionando_despues_de_un_login(
        self, api_client, cliente_user
    ):
        # CARACTERIZACIÓN: last_login queda FUERA del hash de verificación a
        # propósito. Loguearse no debe romper un link de verificación pendiente,
        # y este es justo el flujo normal (register loguea y manda el mail).
        from users.tokens import email_verification_token

        token = email_verification_token.make_token(cliente_user)

        login = api_client.post(
            reverse("login"),
            {"email": cliente_user.email, "password": "ClaveTest123"},
            format="json",
        )
        assert login.status_code == status.HTTP_200_OK

        response = api_client.post(
            reverse("verify_email"),
            {"uid": _uid(cliente_user), "token": token},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        cliente_user.refresh_from_db()
        assert cliente_user.email_verified is True

    def test_cambiar_el_email_invalida_el_token_de_verify(
        self, api_client, cliente_user
    ):
        # El email entra al hash: un link emitido para una dirección no puede
        # confirmar otra.
        from users.tokens import email_verification_token

        token = email_verification_token.make_token(cliente_user)
        cliente_user.email = "otro-email@test.pe"
        cliente_user.save(update_fields=["email"])

        response = api_client.post(
            reverse("verify_email"),
            {"uid": _uid(cliente_user), "token": token},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        cliente_user.refresh_from_db()
        assert cliente_user.email_verified is False


# ---------- El login actualiza last_login ----------


@pytest.mark.django_db
class TestLoginActualizaLastLogin:
    def test_login_exitoso_setea_last_login(self, api_client, cliente_user):
        assert cliente_user.last_login is None

        response = api_client.post(
            reverse("login"),
            {"email": cliente_user.email, "password": "ClaveTest123"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        cliente_user.refresh_from_db()
        assert cliente_user.last_login is not None

    def test_login_no_setea_last_login_si_las_credenciales_fallan(
        self, api_client, cliente_user
    ):
        response = api_client.post(
            reverse("login"),
            {"email": cliente_user.email, "password": "ClaveIncorrecta"},
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        cliente_user.refresh_from_db()
        assert cliente_user.last_login is None

    def test_reset_pedido_antes_de_un_login_muere_al_loguearse(
        self, api_client, cliente_user
    ):
        # last_login SÍ entra al hash del token de reset (es de Django). Que un
        # login invalide los resets pendientes es deseable: si alguien pidió un
        # reset y el dueño real entró con su contraseña, el link queda muerto.
        from django.contrib.auth.tokens import default_token_generator

        token_reset = default_token_generator.make_token(cliente_user)

        login = api_client.post(
            reverse("login"),
            {"email": cliente_user.email, "password": "ClaveTest123"},
            format="json",
        )
        assert login.status_code == status.HTTP_200_OK

        response = api_client.post(
            reverse("password_reset_confirm"),
            {
                "uid": _uid(cliente_user),
                "token": token_reset,
                "new_password": "PasswordNuevo456",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        cliente_user.refresh_from_db()
        assert cliente_user.check_password("PasswordNuevo456") is False
