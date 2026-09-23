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


def _confirm_url(booking):
    return f"/api/bookings/{booking.id}/confirm/"


@pytest.fixture
def category(db):
    return Category.objects.create(name="Peluquería Test")


@pytest.fixture
def business(dueno_user, category):
    return Business.objects.create(
        owner=dueno_user,
        category=category,
        name="Salón Confirm",
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


# --- Camino feliz ---------------------------------------------------------


def test_dueno_confirma_su_booking_pending_devuelve_200_y_persiste(
    api_client, dueno_user, business, _booking
):
    booking = _booking(Booking.Status.PENDING, business)

    api_client.force_authenticate(user=dueno_user)
    response = api_client.post(_confirm_url(booking))

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"

    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED


# --- Transición ilegal ------------------------------------------------


@pytest.mark.parametrize(
    "origen",
    [
        Booking.Status.CONFIRMED,
        Booking.Status.CANCELLED,
        Booking.Status.COMPLETED,
        Booking.Status.NO_SHOW,
    ],
    ids=lambda s: s.value,
)
def test_dueno_confirma_booking_en_estado_ilegal_devuelve_409(
    api_client, dueno_user, business, _booking, origen
):
    booking = _booking(origen, business)

    api_client.force_authenticate(user=dueno_user)
    response = api_client.post(_confirm_url(booking))

    assert response.status_code == 409
    assert response.json()["code"] == "invalid_transition"

    booking.refresh_from_db()
    assert booking.status == origen


# --- Ataques / permisos -------------------------------------------------


def test_cliente_autenticado_no_puede_confirmar_da_403(
    api_client, cliente_user, business, _booking
):
    booking = _booking(Booking.Status.PENDING, business)

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(_confirm_url(booking))

    assert response.status_code == 403

    booking.refresh_from_db()
    assert booking.status == Booking.Status.PENDING


def test_dueno_ajeno_confirma_booking_de_otro_negocio_da_404(
    api_client, otro_dueno, business, _booking
):
    booking = _booking(Booking.Status.PENDING, business)

    api_client.force_authenticate(user=otro_dueno)
    response = api_client.post(_confirm_url(booking))

    assert response.status_code == 404

    booking.refresh_from_db()
    assert booking.status == Booking.Status.PENDING


def test_sin_autenticacion_da_401(api_client, business, _booking):
    booking = _booking(Booking.Status.PENDING, business)

    response = api_client.post(_confirm_url(booking))

    assert response.status_code == 401

    booking.refresh_from_db()
    assert booking.status == Booking.Status.PENDING


def test_pk_inexistente_da_404(api_client, dueno_user):
    api_client.force_authenticate(user=dueno_user)
    response = api_client.post("/api/bookings/999999/confirm/")

    assert response.status_code == 404
