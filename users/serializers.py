from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from .models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode


class RegisterSerializer(serializers.ModelSerializer):
    # write_only: el password entra pero jamás se serializa de vuelta en una respuesta.
    # validators=[validate_password]: aplica los AUTH_PASSWORD_VALIDATORS de settings
    # (longitud mínima, no común, no 100% numérica) en el momento de registrar.
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
        style={
            "input_type": "password"
        },  # cosmético: oculta el campo en la API navegable de DRF
    )

    class Meta:
        model = User
        fields = ("id", "email", "password", "phone")
        # role NO está en fields a propósito: un usuario que se registra NUNCA
        # debe poder elegir su rol (si no, cualquiera se haría platform_admin).
        # El rol lo asigna el sistema -> default "cliente" del modelo/manager.
        read_only_fields = ("id",)

    def create(self, validated_data):
        # Usamos el manager, NO User.objects.create(): create_user se encarga de
        # hashear el password con set_password. Si usáramos create() a secas,
        # guardaríamos el password en texto plano -> agujero de seguridad grave.
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    # Serializer (no ModelSerializer) porque NO mapea a una tabla: solo valida
    # un par email/password contra el sistema de auth. No crea ni edita nada.
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )

    def validate(self, attrs):
        # validate() (sin sufijo de campo) valida el conjunto: acá tiene sentido
        # porque la credencial es la COMBINACIÓN email+password, no cada uno suelto.
        email = attrs.get("email")
        password = attrs.get("password")

        # authenticate() respeta USERNAME_FIELD="email", así que le pasamos email.
        # Internamente hashea el password recibido y lo compara con el guardado.
        user = authenticate(
            request=self.context.get("request"),
            username=email,  # 'username' es el nombre del kwarg, pero authenticate usa USERNAME_FIELD
            password=password,
        )

        if not user:
            # Mensaje GENÉRICO a propósito: no revelamos si falló el email o el
            # password. Decir "ese email no existe" le confirma a un atacante qué
            # correos están registrados (enumeración de usuarios).
            raise AuthenticationFailed("Credenciales inválidas.")

        if not user.is_active:
            raise serializers.ValidationError(
                "Esta cuenta está desactivada.", code="authorization"
            )

        # Guardamos el user validado en attrs para que la view lo use (genera el JWT).
        attrs["user"] = user
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    """Paso 1: el usuario pide resetear. Solo valida que el email tenga formato.
    NO valida que el email exista (a propósito, ver el por qué abajo)."""

    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Paso 2: el usuario llega con el token del email + su nueva password."""

    uid = serializers.CharField()  # id del usuario, codificado en base64
    token = serializers.CharField()  # el token de PasswordResetTokenGenerator
    new_password = serializers.CharField(
        write_only=True,
        validators=[validate_password],  # mismas reglas de fortaleza que en register
    )

    def validate(self, attrs):
        # 1. Decodificar el uid (viene en base64 para que sea seguro en una URL)
        try:
            uid = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            # Token/uid inválido -> mensaje genérico, no revelamos detalles
            raise serializers.ValidationError(
                {"token": "El enlace es inválido o expiró."}
            )

        # 2. Verificar que el token corresponda a este usuario y siga válido
        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError(
                {"token": "El enlace es inválido o expiró."}
            )

        attrs["user"] = user
        return attrs

    def save(self):
        user = self.validated_data["user"]
        user.set_password(
            self.validated_data["new_password"]
        )  # hashea la nueva password
        user.save()
        # Al guardar el nuevo password, el token usado queda inválido automáticamente
        # (su firma se derivaba del password viejo). Un solo uso, gratis.
        return user


class EmailVerifyConfirmSerializer(serializers.Serializer):
    """Confirma la verificación: llega con uid + token del email."""

    uid = serializers.CharField()
    token = serializers.CharField()

    def validate(self, attrs):
        try:
            uid = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            raise serializers.ValidationError(
                {"token": "El enlace es inválido o expiró."}
            )

        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError(
                {"token": "El enlace es inválido o expiró."}
            )

        attrs["user"] = user
        return attrs

    def save(self):
        user = self.validated_data["user"]
        user.email_verified = (
            True  # el único cambio real: sellar el email como verificado
        )
        user.save(update_fields=["email_verified"])
        return user


class EmailVerifyResendSerializer(serializers.Serializer):
    """Para reenviar el email de verificación si el usuario lo perdió."""

    email = serializers.EmailField()
