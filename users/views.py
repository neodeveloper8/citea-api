# Create your views here.
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.core.mail import send_mail
from django.conf import settings
from .models import User
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    EmailVerifyResendSerializer,
    EmailVerifyConfirmSerializer,
)


def get_tokens_for_user(user):
    """Genera el par access+refresh para un usuario ya validado.
    Lo aislamos en una función porque register Y login lo necesitan:
    register para loguear automáticamente tras crear la cuenta, login obviamente."""
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


class RegisterView(generics.CreateAPIView):
    # CreateAPIView nos da el flujo POST estándar (validar serializer -> crear),
    # pero sobrescribimos create() para devolver también los tokens.
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]  # endpoint público: anula el IsAuthenticated global

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(
            raise_exception=True
        )  # si falla -> tu custom_exception_handler
        user = serializer.save()
        send_verification_email(
            user
        )  # enviamos el email de verificación al registrarse
        # Logueamos automáticamente al recién registrado: mejor UX que pedirle
        # que vaya a la pantalla de login justo después de registrarse.
        tokens = get_tokens_for_user(user)

        return Response(
            {
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "role": user.role,
                    "email_verified": user.email_verified,
                },
                "tokens": tokens,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    # APIView (no genérica) porque login no es un CRUD: solo valida credenciales
    # y emite tokens. No mapea a "crear/listar/editar" un recurso.
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(
            raise_exception=True
        )  # credenciales malas -> handler -> formato estándar

        user = serializer.validated_data[
            "user"
        ]  # el user que el serializer validó y guardó en attrs
        tokens = get_tokens_for_user(user)

        return Response(
            {
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "role": user.role,
                },
                "tokens": tokens,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    # IsAuthenticated (no AllowAny): solo un usuario logueado puede desloguearse.
    # Hereda el default global, pero lo pongo explícito para que se lea la intención.
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")

        if not refresh_token:
            # No mandó el refresh -> no hay nada que invalidar. Error claro.
            return Response(
                {
                    "error": "Se requiere el refresh token.",
                    "code": "refresh_required",
                    "details": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)  # parsea y valida el refresh
            token.blacklist()  # lo mete en la blacklist -> ya no sirve
        except TokenError:
            # El token ya estaba expirado, malformado, o ya en blacklist.
            # Da igual: el objetivo (que no se pueda usar) ya se cumple. Respondemos OK.
            pass

        return Response(
            {"detail": "Sesión cerrada correctamente."},
            status=status.HTTP_205_RESET_CONTENT,
        )


class PasswordResetRequestView(APIView):
    permission_classes = [
        AllowAny
    ]  # público: lógico, no estás logueado si olvidaste tu pass
    throttle_scope = "password_reset"  # usa el rate "3/hour" que definimos en settings

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        # Buscamos el usuario, pero si NO existe, NO fallamos (ver por qué abajo)
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            user = None

        if user:
            # Generamos uid (base64) + token, y armamos el link al frontend
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_link = (
                f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
            )

            send_mail(
                subject="Recupera tu contraseña — Citea",
                message=f"Hola, para restablecer tu contraseña entra a: {reset_link}\n\nSi no lo solicitaste, ignora este correo.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )

        # SIEMPRE respondemos lo mismo, exista o no el email (ver por qué abajo)
        return Response(
            {
                "detail": "Si el correo está registrado, recibirás un enlace para restablecer tu contraseña."
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "Tu contraseña fue restablecida correctamente."},
            status=status.HTTP_200_OK,
        )


def send_verification_email(user):
    """Genera token + link y envía el email de verificación.
    Aislado porque se usa en RegisterView (auto) y en EmailVerifyResendView (manual)."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    verify_link = f"{settings.FRONTEND_URL}/verify-email?uid={uid}&token={token}"

    send_mail(
        subject="Verifica tu correo — Citea",
        message=f"Hola, confirma tu correo entrando a: {verify_link}\n\nSi no creaste esta cuenta, ignora este correo.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


class EmailVerifyConfirmView(APIView):
    permission_classes = [AllowAny]  # llega desde un link del email, sin sesión activa

    def post(self, request):
        serializer = EmailVerifyConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Tu correo fue verificado correctamente."},
            status=status.HTTP_200_OK,
        )


class EmailVerifyResendView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = (
        "password_reset"  # reusamos el límite 3/hora (mismo riesgo de spam)
    )

    def post(self, request):
        serializer = EmailVerifyResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            user = None

        # Solo reenviamos si existe Y aún no está verificado (no spamear ya verificados)
        if user and not user.email_verified:
            send_verification_email(user)

        # Respuesta genérica siempre (misma lógica de seguridad que el reset)
        return Response(
            {
                "detail": "Si el correo está registrado y sin verificar, recibirás un nuevo enlace."
            },
            status=status.HTTP_200_OK,
        )
