from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.exceptions import APIException, ValidationError
from rest_framework import status


class ServiceHasBookings(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "Este servicio tiene reservas asociadas y no se puede borrar. "
        "Desactivalo (is_active=False) para ocultarlo del público."
    )
    default_code = "service_has_bookings"


class SlotJustTaken(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "Ese horario acaba de ser reservado por otra persona. "
        "Actualizá la disponibilidad e intentá de nuevo."
    )
    default_code = "slot_just_taken"


class TransicionNoPermitida(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "La transición solicitada no es válida para el estado actual de la reserva."
    )
    default_code = "transicion_no_permitida"


class ReviewDuplicada(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Ya existe una reseña para esta reserva."
    default_code = "review_duplicada"


class RespuestaDuplicada(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Esta reseña ya tiene una respuesta."
    default_code = "respuesta_duplicada"


class ClienteRestringido(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = (
        "No podés reservar en este negocio: tenés inasistencias "
        "recientes registradas."
    )
    default_code = "cliente_restringido"


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
