from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.settings import api_settings
from rest_framework.views import exception_handler as drf_exception_handler

# Mensaje genérico para validaciones con más de un campo: no tiene sentido
# elegir uno arbitrario, el frontend mapea details a cada input.
MENSAJE_VALIDACION_GENERICO = "Los datos enviados no son válidos."

# Clave donde se agrupan los errores que no pertenecen a un campo concreto.
# Se lee de api_settings para respetar el NON_FIELD_ERRORS_KEY configurado,
# en vez de hardcodear "non_field_errors".
CLAVE_NO_CAMPO = api_settings.NON_FIELD_ERRORS_KEY


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
    default_code = "invalid_transition"


class ReviewDuplicada(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Ya existe una reseña para esta reserva."
    default_code = "duplicate_review"


class RespuestaDuplicada(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Esta reseña ya tiene una respuesta."
    default_code = "duplicate_response"


class ClienteRestringido(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = (
        "No podés reservar en este negocio: tenés inasistencias "
        "recientes registradas."
    )
    default_code = "customer_restricted"


def _es_lista_posicional(valor):
    """
    True si el valor es una lista que representa items POSICIONALES (una lista
    de dicts de errores), no una lista de mensajes.

    DRF usa las dos formas con el mismo tipo: ["muy corta"] son mensajes de un
    campo, pero [{}, {"close_time": [...]}, {}] son errores por índice de un
    serializer con many=True. La única forma de distinguirlas es mirar si hay
    dicts adentro.
    """
    return isinstance(valor, list) and any(
        isinstance(elemento, dict) for elemento in valor
    )


def _indexar_items(lista):
    """
    Convierte una lista posicional de errores en un dict indexado por posición.

    POR QUÉ: el contrato exige que "details" sea SIEMPRE un dict. Un
    serializer con many=True (ej. el PUT de hours) devuelve una lista donde la
    POSICIÓN es el dato: [{}, {"close_time": [...]}, {}] significa "el item 1
    falló". Si la aplanáramos se perdería qué item fue. La envolvemos en
    {"items": {"1": {...}}} con las claves como string (JSON no admite claves
    numéricas) y descartando los índices vacíos, que solo son relleno de DRF
    para mantener el alineamiento posicional.
    """
    items = {}
    for indice, elemento in enumerate(lista):
        normalizado = _normalizar_detalle(elemento)
        if normalizado:
            items[str(indice)] = normalizado
    return {"items": items}


def _normalizar_valor(valor):
    """Normaliza el VALOR de un campo dentro de un dict de errores."""
    # ErrorDetail hereda de str, así que este isinstance cubre los dos casos.
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, dict):
        return _normalizar_detalle(valor)
    if _es_lista_posicional(valor):
        return _indexar_items(valor)
    if isinstance(valor, list):
        # Lista de mensajes: ya es la forma que espera el frontend.
        return valor
    # Cualquier otro tipo (int, None...) se envuelve para no romper el contrato
    # "los mensajes de un campo son una lista".
    return [valor]


def _normalizar_detalle(detalle):
    """
    Lleva cualquier forma de ValidationError.detail a un dict.

    DRF devuelve dict, lista de mensajes, lista de dicts o un string suelto
    según por dónde se levantó el error. El frontend no puede ramificar por
    tipo en cada request, así que acá se unifica a dict y solo a dict.
    """
    if isinstance(detalle, dict):
        return {clave: _normalizar_valor(valor) for clave, valor in detalle.items()}
    if _es_lista_posicional(detalle):
        return _indexar_items(detalle)
    if isinstance(detalle, list):
        # Lista de mensajes en la raíz: son errores sin campo asociado.
        return {CLAVE_NO_CAMPO: list(detalle)}
    # String suelto en la raíz (ej. raise ValidationError("msg") en una view).
    return {CLAVE_NO_CAMPO: [detalle]}


def _mensaje_de_validacion(details):
    """
    Elige el string de "error" para una validación.

    Si el único error es de no-campo, ese mensaje ES el mensaje del error y
    mostrarlo es mejor que un genérico ("Hay franjas que se solapan" dice algo,
    "Los datos enviados no son válidos" no). Con varios campos no hay un
    mensaje único razonable: gana el genérico y el detalle vive en details.
    """
    mensajes = details.get(CLAVE_NO_CAMPO)
    if set(details) == {CLAVE_NO_CAMPO} and isinstance(mensajes, list) and mensajes:
        return str(mensajes[0])
    return MENSAJE_VALIDACION_GENERICO


def custom_exception_handler(exc, context):
    """
    Handler de errores de Citea. Contrato: TODA respuesta de error tiene
    exactamente las claves {"error", "code", "details"}, y "details" es
    SIEMPRE un dict (puede estar vacío, nunca es una lista ni None).
    """
    # 1. Conversión PREVIA de las excepciones de Django a las de DRF.
    #
    #    POR QUÉ no dejamos que lo haga DRF: su exception_handler hace
    #    exc = exceptions.NotFound(*(exc.args)) sobre una variable LOCAL, así
    #    que acá seguiríamos viendo la Http404 original, que no tiene
    #    default_code, y todos los 404 saldrían con code "error".
    #
    #    POR QUÉ sin argumentos: DRF reenvía los args de la Http404 como
    #    detail, y esos args son texto interno del backend que termina en la
    #    respuesta al cliente. Un raise Http404("no es tu negocio") filtraría
    #    justo lo que se quería ocultar. Descartamos el mensaje y usamos el
    #    default_detail neutro de DRF.
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    # 2. DRF arma el Response con el status correcto y setea los headers
    #    (WWW-Authenticate, Retry-After) además de llamar a set_rollback().
    response = drf_exception_handler(exc, context)

    # 3. None = excepción que DRF no maneja, o sea un 500 real. La dejamos
    #    propagar: en dev se ve el traceback y no enmascaramos bugs.
    if response is None:
        return None

    detalle = getattr(exc, "detail", None)

    if isinstance(exc, ValidationError):
        code = "validation_error"
        details = _normalizar_detalle(detalle)
        error_message = _mensaje_de_validacion(details)
    else:
        # exc.detail.code respeta un code= pasado a la instancia
        # (SlotJustTaken(code="otro")); default_code es el de la clase.
        code = getattr(detalle, "code", None) or getattr(exc, "default_code", "error")
        if isinstance(detalle, str):
            error_message = str(detalle)
        else:
            # detail no es un mensaje (dict/lista): caemos al texto de la clase.
            error_message = str(getattr(exc, "default_detail", "Ocurrió un error."))

        # Throttled trae el tiempo de espera y el frontend lo necesita para
        # mostrar "reintentá en X". Ya viene redondeado con math.ceil por DRF.
        if isinstance(exc, exceptions.Throttled) and exc.wait is not None:
            details = {"wait": exc.wait}
        else:
            details = {}

    # No tocamos response.headers: los puso DRF en el paso 2.
    response.data = {
        "error": error_message,
        "code": code,
        "details": details,
    }
    return response
