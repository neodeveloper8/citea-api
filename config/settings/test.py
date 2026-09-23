from .base import *  # noqa

# Postgres en Docker (docker-compose.yml, servicio db-test, puerto 5433).
# NO es SQLite: los tests necesitan features de Postgres que SQLite no tiene
# (ExclusionConstraint con rangos para el solape de reservas). Los datos van
# en tmpfs, así que se crean y destruyen en RAM y no tocan Supabase.
# Decisión 31.
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
    # El frontend manda JSON: los tests tienen que ejercitar el mismo encoder.
    # El default de DRF es multipart, que convierte todo a string y esconde
    # errores de tipo (None, bool, int, listas anidadas). multipart queda solo
    # para los uploads, que lo declaran explícito.
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

# sync=True: las tasks corren en el MISMO proceso del test, de forma síncrona.
# Sin esto haría falta un qcluster real levantado para que se ejecuten.
Q_CLUSTER = {
    **Q_CLUSTER,  # hereda lo de base
    "sync": True,
}
