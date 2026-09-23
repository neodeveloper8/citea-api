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


def _cancel_url(booking):
    return f"/api/bookings/{booking.id}/cancel/"


@pytest.fixture
def category(db):
    return Category.objects.create(name="Peluquería Test")


@pytest.fixture
def business(dueno_user, category):
    return Business.objects.create(
        owner=dueno_user,
        category=category,
        name="Salón Cancel",
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
def otro_cliente(db):
    return User.objects.create_user(
        email="otro-cliente@test.pe",
        password="ClaveTest123",
    )


@pytest.fixture
def otro_dueno(db):
    return User.objects.create_user(
        email="otro-dueno@test.pe",
        password="ClaveTest123",
        role=User.Role.DUENO,
    )


@pytest.fixture
def _booking(service):
    def crear(status, customer, business):
        inicio = _aware(time(11, 0))
        fin = _aware(time(11, 30))
        return Booking.objects.create(
            customer=customer,
            business=business,
            service=service,
            start_datetime=inicio,
            end_datetime=fin,
            price_at_booking=service.price,
            duration_at_booking=service.duration_minutes,
            status=status,
        )

    return crear


# --- Camino feliz ---------------------------------------------------------


def test_cliente_cancela_su_booking_pending_devuelve_200_y_persiste(
    api_client, cliente_user, business, _booking
):
    booking = _booking(Booking.Status.PENDING, cliente_user, business)

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(_cancel_url(booking))

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED


def test_cliente_cancela_su_booking_confirmed_devuelve_200_y_persiste(
    api_client, cliente_user, business, _booking
):
    booking = _booking(Booking.Status.CONFIRMED, cliente_user, business)

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(_cancel_url(booking))

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED


def test_dueno_cancela_booking_pending_de_su_negocio_devuelve_200_y_persiste(
    api_client, dueno_user, cliente_user, business, _booking
):
    booking = _booking(Booking.Status.PENDING, cliente_user, business)

    api_client.force_authenticate(user=dueno_user)
    response = api_client.post(_cancel_url(booking))

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED


def test_dueno_cancela_booking_confirmed_de_su_negocio_devuelve_200_y_persiste(
    api_client, dueno_user, cliente_user, business, _booking
):
    booking = _booking(Booking.Status.CONFIRMED, cliente_user, business)

    api_client.force_authenticate(user=dueno_user)
    response = api_client.post(_cancel_url(booking))

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED


# --- Estado terminal --------------------------------------------------


@pytest.mark.parametrize(
    "origen",
    [Booking.Status.CANCELLED, Booking.Status.COMPLETED, Booking.Status.NO_SHOW],
    ids=lambda s: s.value,
)
def test_cliente_cancela_booking_en_estado_terminal_devuelve_409(
    api_client, cliente_user, business, _booking, origen
):
    booking = _booking(origen, cliente_user, business)

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(_cancel_url(booking))

    assert response.status_code == 409
    assert response.json()["code"] == "invalid_transition"

    booking.refresh_from_db()
    assert booking.status == origen


# --- Ataques / permisos -------------------------------------------------


def test_otro_cliente_ajeno_da_404(
    api_client, otro_cliente, cliente_user, business, _booking
):
    booking = _booking(Booking.Status.PENDING, cliente_user, business)

    api_client.force_authenticate(user=otro_cliente)
    response = api_client.post(_cancel_url(booking))

    assert response.status_code == 404

    booking.refresh_from_db()
    assert booking.status == Booking.Status.PENDING


def test_otro_dueno_ajeno_a_la_reserva_da_404(
    api_client, otro_dueno, cliente_user, business, _booking
):
    booking = _booking(Booking.Status.PENDING, cliente_user, business)

    api_client.force_authenticate(user=otro_dueno)
    response = api_client.post(_cancel_url(booking))

    assert response.status_code == 404

    booking.refresh_from_db()
    assert booking.status == Booking.Status.PENDING


def test_sin_autenticacion_da_401(api_client, cliente_user, business, _booking):
    booking = _booking(Booking.Status.PENDING, cliente_user, business)

    response = api_client.post(_cancel_url(booking))

    assert response.status_code == 401

    booking.refresh_from_db()
    assert booking.status == Booking.Status.PENDING


def test_pk_inexistente_como_customer_da_404(api_client, cliente_user):
    api_client.force_authenticate(user=cliente_user)
    response = api_client.post("/api/bookings/999999/cancel/")

    assert response.status_code == 404
