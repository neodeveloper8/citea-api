from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from bookings.models import Booking
from businesses.models import Business, Category, Service
from users.models import User

pytestmark = pytest.mark.django_db

LIMA_TZ = ZoneInfo("America/Lima")


def _aware(hora):
    fecha = date.today() + timedelta(days=1)
    return datetime.combine(fecha, hora, tzinfo=LIMA_TZ)


def _complete_url(booking):
    return f"/api/bookings/{booking.id}/complete/"


def _no_show_url(booking):
    return f"/api/bookings/{booking.id}/no-show/"


@pytest.fixture
def category(db):
    return Category.objects.create(name="Peluquería Test")


@pytest.fixture
def business(dueno_user, category):
    return Business.objects.create(
        owner=dueno_user,
        category=category,
        name="Salón Complete/NoShow",
    )


@pytest.fixture
def service(business):
    return Service.objects.create(
        business=business,
        name="Corte",
        duration_minutes=30,
        price="20.00",
    )


@pytest.fixture
def otro_dueno(db):
    return User.objects.create_user(
        email="otro-dueno@test.pe",
        password="ClaveTest123",
        role=User.Role.DUENO,
    )


@pytest.fixture
def _booking(cliente_user, service):
    def crear(status, owner_business):
        inicio = _aware(time(11, 0))
        fin = _aware(time(11, 30))
        return Booking.objects.create(
            customer=cliente_user,
            business=owner_business,
            service=service,
            start_datetime=inicio,
            end_datetime=fin,
            price_at_booking=service.price,
            duration_at_booking=service.duration_minutes,
            status=status,
        )

    return crear


ESTADOS_ILEGALES_COMUNES = [
    Booking.Status.PENDING,
    Booking.Status.CANCELLED,
    Booking.Status.COMPLETED,
    Booking.Status.NO_SHOW,
]


# --- complete/ ------------------------------------------------------------


def test_dueno_completa_su_booking_confirmed_devuelve_200_y_persiste(
    api_client, dueno_user, business, _booking
):
    booking = _booking(Booking.Status.CONFIRMED, business)

    api_client.force_authenticate(user=dueno_user)
    response = api_client.post(_complete_url(booking))

    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    booking.refresh_from_db()
    assert booking.status == Booking.Status.COMPLETED


@pytest.mark.parametrize("origen", ESTADOS_ILEGALES_COMUNES, ids=lambda s: s.value)
def test_dueno_completa_booking_en_estado_ilegal_devuelve_409(
    api_client, dueno_user, business, _booking, origen
):
    booking = _booking(origen, business)

    api_client.force_authenticate(user=dueno_user)
    response = api_client.post(_complete_url(booking))

    assert response.status_code == 409
    assert response.json()["code"] == "transicion_no_permitida"

    booking.refresh_from_db()
    assert booking.status == origen


def test_complete_cliente_autenticado_da_403(
    api_client, cliente_user, business, _booking
):
    booking = _booking(Booking.Status.CONFIRMED, business)

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(_complete_url(booking))

    assert response.status_code == 403

    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED


def test_complete_dueno_ajeno_da_404(api_client, otro_dueno, business, _booking):
    booking = _booking(Booking.Status.CONFIRMED, business)

    api_client.force_authenticate(user=otro_dueno)
    response = api_client.post(_complete_url(booking))

    assert response.status_code == 404

    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED


def test_complete_sin_autenticacion_da_401(api_client, business, _booking):
    booking = _booking(Booking.Status.CONFIRMED, business)

    response = api_client.post(_complete_url(booking))

    assert response.status_code == 401

    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED


# --- no-show/ ---------------------------------------------------------


def test_dueno_marca_no_show_su_booking_confirmed_devuelve_200_y_persiste(
    api_client, dueno_user, business, _booking
):
    booking = _booking(Booking.Status.CONFIRMED, business)

    api_client.force_authenticate(user=dueno_user)
    response = api_client.post(_no_show_url(booking))

    assert response.status_code == 200
    assert response.json()["status"] == "no_show"

    booking.refresh_from_db()
    assert booking.status == Booking.Status.NO_SHOW


@pytest.mark.parametrize("origen", ESTADOS_ILEGALES_COMUNES, ids=lambda s: s.value)
def test_dueno_marca_no_show_en_estado_ilegal_devuelve_409(
    api_client, dueno_user, business, _booking, origen
):
    booking = _booking(origen, business)

    api_client.force_authenticate(user=dueno_user)
    response = api_client.post(_no_show_url(booking))

    assert response.status_code == 409
    assert response.json()["code"] == "transicion_no_permitida"

    booking.refresh_from_db()
    assert booking.status == origen


def test_no_show_cliente_autenticado_da_403(
    api_client, cliente_user, business, _booking
):
    booking = _booking(Booking.Status.CONFIRMED, business)

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(_no_show_url(booking))

    assert response.status_code == 403

    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED


def test_no_show_dueno_ajeno_da_404(api_client, otro_dueno, business, _booking):
    booking = _booking(Booking.Status.CONFIRMED, business)

    api_client.force_authenticate(user=otro_dueno)
    response = api_client.post(_no_show_url(booking))

    assert response.status_code == 404

    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED


def test_no_show_sin_autenticacion_da_401(api_client, business, _booking):
    booking = _booking(Booking.Status.CONFIRMED, business)

    response = api_client.post(_no_show_url(booking))

    assert response.status_code == 401

    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED
