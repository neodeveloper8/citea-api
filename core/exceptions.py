from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.exceptions import ValidationError


def custom_exception_handler(exc, context):
    # 1. Dejamos que DRF maneje la excepción primero. Nos devuelve un Response
    #    con el status code correcto (400, 401, 403, 404...) y el cuerpo en SU formato.
    response = drf_exception_handler(exc, context)

    # 2. Si DRF devuelve None, es una excepción que él NO sabe manejar
    #    (ej. un error de Python no controlado -> un 500 real).
    #    La dejamos pasar: en dev verás el traceback completo, y no enmascaramos bugs.
    if response is None:
        return None

    # 3. Reempaquetamos al formato estándar de Citea.
    #    default_code es un string máquina-legible que traen las excepciones DRF
    #    (ej. "not_authenticated", "permission_denied", "not_found").
    code = getattr(exc, "default_code", "error")
    details = {}

    if isinstance(exc, ValidationError):
        # Los errores de validación traen el detalle por campo:
        # {"email": ["ya existe"], "password": ["muy corta"]}
        # Eso va tal cual en "details" para que el frontend lo mapee a cada input.
        error_message = "Los datos enviados no son válidos."
        code = "validation_error"
        details = response.data
    else:
        # El resto de excepciones DRF traen {"detail": "mensaje legible"}.
        detail = response.data.get("detail", "Ocurrió un error.")
        error_message = str(detail)

    response.data = {
        "error": error_message,
        "code": code,
        "details": details,
    }
    return response
