from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.db import IntegrityError, transaction

from bookings.models import Booking, Review
from businesses.models import Business, Category, Service
from users.models import User

pytestmark = pytest.mark.django_db

LIMA_TZ = ZoneInfo("America/Lima")

URL = "/api/reviews/"


def _aware(hora):
    fecha = date.today() + timedelta(days=1)
    return datetime.combine(fecha, hora, tzinfo=LIMA_TZ)


@pytest.fixture
def category(db):
    return Category.objects.create(name="Peluquería Test")


@pytest.fixture
def business(dueno_user, category):
    return Business.objects.create(
        owner=dueno_user,
        category=category,
        name="Salón Reviews",
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
def _booking(business, service):
    def crear(status, customer):
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


# --- Camino feliz -----------------------------------------------------


def test_cliente_resena_su_booking_completed_devuelve_201(
    api_client, cliente_user, _booking
):
    booking = _booking(Booking.Status.COMPLETED, cliente_user)

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(
        URL, {"booking": booking.id, "rating": 5, "comment": "Excelente atención"}
    )

    assert response.status_code == 201
    data = response.json()
    assert "created_at" in data  # confirma que responde con el ReadSerializer

    review = Review.objects.get(booking=booking)
    assert review.rating == 5
    assert review.comment == "Excelente atención"


# --- Estado no completed ------------------------------------------------


@pytest.mark.parametrize(
    "origen",
    [
        Booking.Status.PENDING,
        Booking.Status.CONFIRMED,
        Booking.Status.CANCELLED,
        Booking.Status.NO_SHOW,
    ],
    ids=lambda s: s.value,
)
def test_resenar_booking_no_completed_da_400(
    api_client, cliente_user, _booking, origen
):
    booking = _booking(origen, cliente_user)

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(URL, {"booking": booking.id, "rating": 5})

    assert response.status_code == 400
    assert not Review.objects.filter(booking=booking).exists()


# --- Booking ajeno --------------------------------------------------------


def test_resenar_booking_ajeno_da_400(api_client, otro_cliente, cliente_user, _booking):
    booking = _booking(Booking.Status.COMPLETED, cliente_user)

    api_client.force_authenticate(user=otro_cliente)
    response = api_client.post(URL, {"booking": booking.id, "rating": 5})

    assert response.status_code == 400
    assert not Review.objects.filter(booking=booking).exists()


# --- Ya reseñado ---------------------------------------------------------


def test_resenar_booking_ya_resenado_da_400(api_client, cliente_user, _booking):
    booking = _booking(Booking.Status.COMPLETED, cliente_user)

    api_client.force_authenticate(user=cliente_user)
    primera = api_client.post(URL, {"booking": booking.id, "rating": 4})
    assert primera.status_code == 201

    segunda = api_client.post(URL, {"booking": booking.id, "rating": 2})

    assert segunda.status_code == 400
    assert Review.objects.filter(booking=booking).count() == 1


# --- Rating fuera de rango ---------------------------------------------


@pytest.mark.parametrize("rating_invalido", [0, 6])
def test_rating_fuera_de_rango_da_400(
    api_client, cliente_user, _booking, rating_invalido
):
    booking = _booking(Booking.Status.COMPLETED, cliente_user)

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(URL, {"booking": booking.id, "rating": rating_invalido})

    assert response.status_code == 400


# --- Sin autenticación -----------------------------------------------


def test_sin_autenticacion_da_401(api_client, cliente_user, _booking):
    booking = _booking(Booking.Status.COMPLETED, cliente_user)

    response = api_client.post(URL, {"booking": booking.id, "rating": 5})

    assert response.status_code == 401


# --- A nivel modelo: garantía OneToOne de BD -----------------------------


def test_segunda_review_mismo_booking_levanta_integrity_error(cliente_user, _booking):
    booking = _booking(Booking.Status.COMPLETED, cliente_user)
    Review.objects.create(booking=booking, rating=5, comment="Buena")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Review.objects.create(booking=booking, rating=3, comment="Otra")
