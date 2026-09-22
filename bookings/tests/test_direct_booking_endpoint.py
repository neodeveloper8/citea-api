from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from bookings.models import Booking
from businesses.models import Business, Category, Service
from users.models import User

pytestmark = pytest.mark.django_db

LIMA_TZ = ZoneInfo("America/Lima")

URL = "/api/bookings/direct/"


def _aware_lima(fecha, hora):
    return datetime.combine(fecha, hora, tzinfo=LIMA_TZ)


def _manana():
    return date.today() + timedelta(days=1)


@pytest.fixture
def category(db):
    return Category.objects.create(name="Peluquería Test")


@pytest.fixture
def business(dueno_user, category):
    return Business.objects.create(
        owner=dueno_user,
        category=category,
        name="Salón Direct",
        status=Business.Status.APPROVED,
    )


@pytest.fixture
def otro_dueno(db):
    return User.objects.create_user(
        email="otro-dueno@test.pe", password="ClaveTest123", role=User.Role.DUENO
    )


@pytest.fixture
def service(business):
    return Service.objects.create(
        business=business, name="Corte", duration_minutes=30, price="20.00"
    )


def _payload(
    business, service, inicio, guest_name="Pedro Tel", guest_phone="987654321"
):
    return {
        "business": business.id,
        "service": service.id,
        "start_datetime": inicio.isoformat(),
        "guest_name": guest_name,
        "guest_phone": guest_phone,
    }


# --- Camino feliz -----------------------------------------------------


def test_dueno_crea_direct_devuelve_201_y_persiste(
    api_client, dueno_user, business, service
):
    inicio = _aware_lima(_manana(), time(10, 0))

    api_client.force_authenticate(user=dueno_user)
    response = api_client.post(
        URL, _payload(business, service, inicio, "Pedro Tel", "987654321")
    )

    assert response.status_code == 201
    data = response.json()
    assert data["guest_name"] == "Pedro Tel"

    booking = Booking.objects.get(id=data["id"])
    service.refresh_from_db()
    assert booking.customer is None
    assert booking.source == Booking.Source.DIRECT
    assert booking.status == Booking.Status.CONFIRMED
    assert booking.guest_name == "Pedro Tel"
    assert booking.guest_phone == "987654321"
    assert booking.price_at_booking == service.price
    assert booking.duration_at_booking == service.duration_minutes
    assert booking.end_datetime == inicio + timedelta(minutes=service.duration_minutes)


# --- guest_name obligatorio ----------------------------------------------


@pytest.mark.parametrize("guest_name", ["", "   "])
def test_guest_name_vacio_o_solo_espacios_da_400(
    api_client, dueno_user, business, service, guest_name
):
    inicio = _aware_lima(_manana(), time(10, 0))

    api_client.force_authenticate(user=dueno_user)
    response = api_client.post(
        URL, _payload(business, service, inicio, guest_name=guest_name)
    )

    assert response.status_code == 400


# --- Sin grilla ---------------------------------------------------------


def test_horario_fuera_de_grilla_igual_201(api_client, dueno_user, business, service):
    """direct NO valida grilla: un horario 'raro' (10:07) igual se acepta."""
    inicio = _aware_lima(_manana(), time(10, 7))

    api_client.force_authenticate(user=dueno_user)
    response = api_client.post(URL, _payload(business, service, inicio))

    assert response.status_code == 201


# --- Solape ------------------------------------------------------------


def test_solape_entre_dos_direct_da_409(api_client, dueno_user, business, service):
    inicio = _aware_lima(_manana(), time(10, 0))

    api_client.force_authenticate(user=dueno_user)
    primera = api_client.post(
        URL, _payload(business, service, inicio, "Guest Uno", "111")
    )
    assert primera.status_code == 201

    segunda = api_client.post(
        URL, _payload(business, service, inicio, "Guest Dos", "222")
    )

    assert segunda.status_code == 409
    assert segunda.json()["code"] == "slot_just_taken"


def test_solape_contra_booking_marketplace_da_409(
    api_client, dueno_user, cliente_user, business, service
):
    inicio = _aware_lima(_manana(), time(10, 0))
    fin = inicio + timedelta(minutes=service.duration_minutes)
    Booking.objects.create(
        customer=cliente_user,
        business=business,
        service=service,
        start_datetime=inicio,
        end_datetime=fin,
        price_at_booking=service.price,
        duration_at_booking=service.duration_minutes,
        status=Booking.Status.CONFIRMED,
    )

    api_client.force_authenticate(user=dueno_user)
    response = api_client.post(URL, _payload(business, service, inicio))

    assert response.status_code == 409
    assert response.json()["code"] == "slot_just_taken"


# --- Ownership -----------------------------------------------------------


def test_dueno_ajeno_da_400_no_es_tu_negocio(api_client, otro_dueno, business, service):
    inicio = _aware_lima(_manana(), time(10, 0))

    api_client.force_authenticate(user=otro_dueno)
    response = api_client.post(URL, _payload(business, service, inicio))

    assert response.status_code == 400
    assert not Booking.objects.filter(business=business).exists()


# --- Permisos ---------------------------------------------------------


def test_cliente_autenticado_da_403(api_client, cliente_user, business, service):
    inicio = _aware_lima(_manana(), time(10, 0))

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(URL, _payload(business, service, inicio))

    assert response.status_code == 403


def test_sin_autenticacion_da_401(api_client, business, service):
    inicio = _aware_lima(_manana(), time(10, 0))

    response = api_client.post(URL, _payload(business, service, inicio))

    assert response.status_code == 401


# --- Sin email -----------------------------------------------------------


def test_direct_no_dispara_ningun_email(
    api_client, dueno_user, business, service, mailoutbox
):
    inicio = _aware_lima(_manana(), time(10, 0))

    api_client.force_authenticate(user=dueno_user)
    response = api_client.post(URL, _payload(business, service, inicio))

    assert response.status_code == 201
    assert len(mailoutbox) == 0
