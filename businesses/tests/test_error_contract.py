"""
Contrato de error en endpoints reales de businesses.

Complementa a core/tests/test_exception_handler.py: ahí se prueba el handler
aislado, acá que el formato llegue igual pasando por URLs, views y permisos.
El PUT de hours es el único endpoint con many=True en escritura, o sea el
único que puede producir un ValidationError con forma de lista.
"""

from datetime import time

import pytest
from rest_framework.settings import api_settings

from businesses.models import Business, BusinessHours, Category

pytestmark = pytest.mark.django_db

NO_CAMPO = api_settings.NON_FIELD_ERRORS_KEY

LUNES = 0


def _hours_url(business):
    return f"/api/businesses/{business.slug}/hours/"


@pytest.fixture
def category(db):
    return Category.objects.create(name="Peluquería Contrato")


@pytest.fixture
def business(dueno_user, category):
    return Business.objects.create(
        owner=dueno_user,
        category=category,
        name="Salón Contrato",
        status=Business.Status.APPROVED,
    )


# --- 404 por get_object() del ViewSet -----------------------------------


def test_detail_slug_inexistente_devuelve_not_found(api_client):
    # get_object() de DRF usa el get_object_or_404 de django.shortcuts por
    # debajo, así que el handler recibe una Http404 de Django.
    response = api_client.get("/api/businesses/no-existe-este-slug/")

    data = response.json()
    assert response.status_code == 404
    assert data["code"] == "not_found"
    assert set(data.keys()) == {"error", "code", "details"}
    assert data["details"] == {}


# --- PUT hours: ValidationError con many=True ---------------------------


def test_hours_item_sin_close_time_indexa_el_item_que_fallo(api_client, business):
    api_client.force_authenticate(user=business.owner)
    payload = [
        {"weekday": LUNES, "open_time": "09:00", "close_time": "13:00"},
        {"weekday": 1, "open_time": "09:00"},
        {"weekday": 2, "open_time": "09:00", "close_time": "13:00"},
    ]

    response = api_client.put(_hours_url(business), payload, format="json")

    data = response.json()
    assert response.status_code == 400
    assert data["code"] == "validation_error"
    assert isinstance(data["details"], dict)
    # El índice se conserva: falló el item 1, no "algún" item.
    assert "close_time" in data["details"]["items"]["1"]
    # Los items válidos (0 y 2) no aparecen como ruido.
    assert set(data["details"]["items"]) == {"1"}


def test_hours_franjas_solapadas_usa_el_mensaje_del_solape_como_error(
    api_client, business
):
    api_client.force_authenticate(user=business.owner)
    payload = [
        {"weekday": LUNES, "open_time": "09:00", "close_time": "13:00"},
        {"weekday": LUNES, "open_time": "11:00", "close_time": "15:00"},
    ]

    response = api_client.put(_hours_url(business), payload, format="json")

    data = response.json()
    assert response.status_code == 400
    assert data["code"] == "validation_error"
    # Error de no-campo único: el mensaje real es más útil que el genérico.
    assert "solapan" in data["error"]
    assert NO_CAMPO in data["details"]


def test_hours_payload_dict_en_vez_de_lista_va_a_no_campo(api_client, business):
    api_client.force_authenticate(user=business.owner)
    payload = {"weekday": LUNES, "open_time": "09:00", "close_time": "13:00"}

    response = api_client.put(_hours_url(business), payload, format="json")

    data = response.json()
    assert response.status_code == 400
    assert data["code"] == "validation_error"
    assert isinstance(data["details"], dict)
    assert NO_CAMPO in data["details"]


def test_hours_item_con_close_anterior_al_open_indexa_el_item(api_client, business):
    api_client.force_authenticate(user=business.owner)
    payload = [
        {"weekday": LUNES, "open_time": "09:00", "close_time": "13:00"},
        {"weekday": 1, "open_time": "15:00", "close_time": "10:00"},
    ]

    response = api_client.put(_hours_url(business), payload, format="json")

    data = response.json()
    assert response.status_code == 400
    # El validate() del child produce non_field_errors DENTRO del item.
    assert NO_CAMPO in data["details"]["items"]["1"]


def test_hours_payload_valido_sigue_funcionando(api_client, business):
    # Control: el saneamiento del formato de error no toca el happy path.
    api_client.force_authenticate(user=business.owner)
    payload = [{"weekday": LUNES, "open_time": "09:00", "close_time": "13:00"}]

    response = api_client.put(_hours_url(business), payload, format="json")

    assert response.status_code == 200
    assert BusinessHours.objects.filter(business=business).count() == 1
    assert BusinessHours.objects.get(business=business).open_time == time(9, 0)
