"""
Tests UNITARIOS del custom_exception_handler.

Sin BD a propósito (no usan django_db): el handler es una función pura que
recibe una excepción y devuelve un Response. Llamarlo directo con un context
vacío aísla el formato de cualquier view, URL o modelo.
"""

import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions
from rest_framework.settings import api_settings

from core.exceptions import (
    ClienteRestringido,
    RespuestaDuplicada,
    ReviewDuplicada,
    ServiceHasBookings,
    SlotJustTaken,
    TransicionNoPermitida,
    custom_exception_handler,
)

NO_CAMPO = api_settings.NON_FIELD_ERRORS_KEY
MENSAJE_GENERICO = "Los datos enviados no son válidos."


def manejar(exc):
    """Atajo: corre el handler con un context vacío."""
    return custom_exception_handler(exc, {})


# --------------------------------------------------------------------------
# Excepciones de Django convertidas a las de DRF
# --------------------------------------------------------------------------


def test_http404_de_django_devuelve_404_con_code_not_found():
    response = manejar(Http404())

    assert response.status_code == 404
    assert response.data["code"] == "not_found"
    assert response.data["details"] == {}


def test_http404_no_filtra_su_mensaje_interno():
    # Las views levantan Http404("...") con texto interno para no confirmarle
    # a un no-dueño que el negocio existe. Ese texto NUNCA debe salir.
    response = manejar(Http404("dato interno secreto"))

    assert response.status_code == 404
    assert response.data["code"] == "not_found"
    assert "dato interno secreto" not in response.data["error"]
    assert "dato interno secreto" not in str(response.data)


def test_permission_denied_de_django_devuelve_403_con_code():
    response = manejar(DjangoPermissionDenied())

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


def test_permission_denied_de_django_no_filtra_su_mensaje():
    response = manejar(DjangoPermissionDenied("motivo interno"))

    assert "motivo interno" not in str(response.data)


# --------------------------------------------------------------------------
# Excepciones nativas de DRF
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc, status_esperado, code_esperado",
    [
        (exceptions.NotFound(), 404, "not_found"),
        (exceptions.PermissionDenied(), 403, "permission_denied"),
        (exceptions.NotAuthenticated(), 401, "not_authenticated"),
        (exceptions.AuthenticationFailed(), 401, "authentication_failed"),
        (exceptions.MethodNotAllowed("PUT"), 405, "method_not_allowed"),
        (exceptions.ParseError(), 400, "parse_error"),
    ],
)
def test_excepciones_drf_conservan_su_code(exc, status_esperado, code_esperado):
    response = manejar(exc)

    assert response.status_code == status_esperado
    assert response.data["code"] == code_esperado
    assert response.data["details"] == {}


def test_throttled_expone_el_wait_en_details_y_el_header():
    response = manejar(exceptions.Throttled(wait=30))

    assert response.status_code == 429
    assert response.data["code"] == "throttled"
    assert response.data["details"] == {"wait": 30}
    # El header lo pone DRF; el handler no debe pisarlo.
    assert response.headers["Retry-After"] == "30"


def test_throttled_sin_wait_deja_details_vacio():
    response = manejar(exceptions.Throttled())

    assert response.data["code"] == "throttled"
    assert response.data["details"] == {}


# --------------------------------------------------------------------------
# Excepciones custom de Citea
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc, status_esperado, code_esperado",
    [
        (ServiceHasBookings(), 409, "service_has_bookings"),
        (SlotJustTaken(), 409, "slot_just_taken"),
        (TransicionNoPermitida(), 409, "transicion_no_permitida"),
        (ReviewDuplicada(), 409, "review_duplicada"),
        (RespuestaDuplicada(), 409, "respuesta_duplicada"),
        (ClienteRestringido(), 403, "cliente_restringido"),
    ],
)
def test_excepciones_custom_usan_su_default_code(exc, status_esperado, code_esperado):
    response = manejar(exc)

    assert response.status_code == status_esperado
    assert response.data["code"] == code_esperado


def test_custom_con_code_explicito_gana_sobre_el_default():
    response = manejar(SlotJustTaken(code="otro"))

    assert response.data["code"] == "otro"


def test_custom_usa_su_default_detail_como_error():
    response = manejar(SlotJustTaken())

    assert response.data["error"] == SlotJustTaken.default_detail


# --------------------------------------------------------------------------
# ValidationError: details siempre dict
# --------------------------------------------------------------------------


def test_validation_dict_con_lista_se_deja_igual():
    response = manejar(exceptions.ValidationError({"x": ["mal"]}))

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert response.data["details"] == {"x": ["mal"]}
    assert response.data["error"] == MENSAJE_GENERICO


def test_validation_dict_con_string_se_envuelve_en_lista():
    # Las views levantan ValidationError({"date": "msg"}) con string suelto.
    response = manejar(exceptions.ValidationError({"date": "msg"}))

    assert response.data["details"] == {"date": ["msg"]}


def test_validation_string_en_la_raiz_va_a_no_campo():
    response = manejar(exceptions.ValidationError("msg"))

    assert response.data["details"] == {NO_CAMPO: ["msg"]}
    # Un único error de no-campo ES el mensaje: se muestra en vez del genérico.
    assert response.data["error"] == "msg"


def test_validation_lista_de_strings_en_la_raiz_va_a_no_campo():
    response = manejar(exceptions.ValidationError(["a", "b"]))

    assert response.data["details"] == {NO_CAMPO: ["a", "b"]}
    assert response.data["error"] == "a"


def test_validation_lista_posicional_se_indexa_por_item():
    # Forma real del PUT de hours con many=True: falla el item del medio.
    exc = exceptions.ValidationError([{}, {"close_time": ["req"]}, {}])

    response = manejar(exc)

    assert response.data["details"] == {"items": {"1": {"close_time": ["req"]}}}


def test_validation_lista_posicional_anidada_en_un_campo():
    exc = exceptions.ValidationError({"services": [{}, {"name": ["req"]}]})

    response = manejar(exc)

    assert response.data["details"] == {"services": {"items": {"1": {"name": ["req"]}}}}


def test_validation_solo_no_campo_usa_ese_mensaje_como_error():
    response = manejar(exceptions.ValidationError({NO_CAMPO: ["solape"]}))

    assert response.data["error"] == "solape"
    assert response.data["details"] == {NO_CAMPO: ["solape"]}


def test_validation_no_campo_mas_otro_campo_usa_el_generico():
    # Con más de una clave no hay un mensaje único razonable.
    response = manejar(exceptions.ValidationError({NO_CAMPO: ["x"], "name": ["y"]}))

    assert response.data["error"] == MENSAJE_GENERICO


def test_validation_items_descarta_los_indices_vacios():
    exc = exceptions.ValidationError([{}, {}, {"weekday": ["req"]}])

    response = manejar(exc)

    assert response.data["details"]["items"] == {"2": {"weekday": ["req"]}}


# --------------------------------------------------------------------------
# Lo que el handler NO debe manejar
# --------------------------------------------------------------------------


def test_excepcion_no_api_devuelve_none():
    # Un error de Python no controlado es un 500 real: no lo enmascaramos,
    # así el traceback llega entero a los logs y a dev.
    assert manejar(ValueError("boom")) is None


# --------------------------------------------------------------------------
# INVARIANTE del contrato, sobre todos los casos que devuelven respuesta
# --------------------------------------------------------------------------

CASOS_CON_RESPUESTA = [
    Http404(),
    Http404("interno"),
    DjangoPermissionDenied(),
    exceptions.NotFound(),
    exceptions.PermissionDenied(),
    exceptions.NotAuthenticated(),
    exceptions.AuthenticationFailed(),
    exceptions.MethodNotAllowed("PUT"),
    exceptions.ParseError(),
    exceptions.Throttled(wait=30),
    exceptions.Throttled(),
    ServiceHasBookings(),
    SlotJustTaken(),
    SlotJustTaken(code="otro"),
    TransicionNoPermitida(),
    ReviewDuplicada(),
    RespuestaDuplicada(),
    ClienteRestringido(),
    exceptions.ValidationError({"x": ["mal"]}),
    exceptions.ValidationError({"date": "msg"}),
    exceptions.ValidationError("msg"),
    exceptions.ValidationError(["a", "b"]),
    exceptions.ValidationError([{}, {"close_time": ["req"]}, {}]),
    exceptions.ValidationError({"services": [{}, {"name": ["req"]}]}),
    exceptions.ValidationError({NO_CAMPO: ["solape"]}),
    exceptions.ValidationError({NO_CAMPO: ["x"], "name": ["y"]}),
    exceptions.APIException(),
]


@pytest.mark.parametrize("exc", CASOS_CON_RESPUESTA, ids=lambda e: type(e).__name__)
def test_invariante_del_contrato(exc):
    response = manejar(exc)

    assert set(response.data.keys()) == {"error", "code", "details"}
    assert isinstance(response.data["details"], dict)
    assert isinstance(response.data["error"], str)
    assert isinstance(response.data["code"], str)
