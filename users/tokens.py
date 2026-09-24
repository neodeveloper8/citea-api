from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """Token para confirmar un email. Separado del de reseteo de contraseña.

    Antes los dos flujos usaban default_token_generator, o sea el MISMO
    generador con el MISMO salt, así que sus tokens eran indistinguibles: un
    token emitido para confirmar un email servía tal cual en
    /password-reset/confirm/ y permitía tomar la cuenta. Un mail de bienvenida
    interceptado, o un link que el propio usuario reenvía, alcanzaba.
    """

    # key_salt distinto al de PasswordResetTokenGenerator: entra al
    # salted_hmac(), así que los tokens de los dos flujos dejan de ser
    # intercambiables incluso con los mismos datos y el mismo SECRET_KEY.
    key_salt = "citea.users.tokens.EmailVerificationTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        # email_verified: es lo que hace al token de UN SOLO USO. Al verificar
        #   pasa de False a True, el hash cambia y el token queda muerto. El
        #   generador de Django consigue lo mismo de rebote porque el reseteo
        #   cambia el password; verify no toca el password, así que necesita su
        #   propio dato mutable.
        # email: si el usuario cambia de dirección, el link viejo muere. Sin
        #   esto, un token emitido para una dirección confirmaría otra.
        # FUERA a propósito:
        #   - last_login: loguearse NO debe romper un link de verificación
        #     pendiente, y es el flujo normal (register loguea y manda el mail).
        #   - password: cambiar la contraseña tampoco tiene por qué invalidar
        #     una verificación de email pendiente. Son cosas independientes.
        return f"{user.pk}{user.email}{user.email_verified}{timestamp}"


email_verification_token = EmailVerificationTokenGenerator()
