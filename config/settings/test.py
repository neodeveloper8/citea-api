from .base import *  # noqa

# BD en memoria con SQLite: se crea y destruye al instante, no toca Supabase.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",  # ":memory:" = vive en RAM, no escribe a disco
    }
}

# En tests el email va a un backend en memoria (ni consola ni Resend)
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Hashing rápido: en tests no necesitamos el hashing seguro (lento) de producción.
# Esto acelera MUCHO los tests que crean usuarios.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Desactivar throttling en tests (si no, los tests de muchos requests fallarían)
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # hereda lo de base
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {},
}
