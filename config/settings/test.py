from .base import *  # noqa

# BD en memoria con SQLite: se crea y destruye al instante, no toca Supabase.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "citea",
        "USER": "citea",
        "PASSWORD": "citea",
        "HOST": "localhost",
        "PORT": "5433",
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

# sync=True: las tasks corren en el MISMO proceso del test, de forma síncrona.
# Sin esto haría falta un qcluster real levantado para que se ejecuten.
Q_CLUSTER = {
    **Q_CLUSTER,  # hereda lo de base
    "sync": True,
}
