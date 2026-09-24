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


def test_resenar_booking_ya_resenado_da_409(api_client, cliente_user, _booking):
    booking = _booking(Booking.Status.COMPLETED, cliente_user)

    api_client.force_authenticate(user=cliente_user)
    primera = api_client.post(URL, {"booking": booking.id, "rating": 4})
    assert primera.status_code == 201

    segunda = api_client.post(URL, {"booking": booking.id, "rating": 2})

    # Duplicar es un conflicto de estado, no un dato mal formado.
    data = segunda.json()
    assert segunda.status_code == 409
    assert data["code"] == "duplicate_review"
    assert data["details"] == {}
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


# --- Precedencia: un 409 no puede tapar un 400 ---------------------------


def test_review_duplicada_con_rating_invalido_da_400_no_409(
    api_client, cliente_user, _booking
):
    # ATAQUE: si el chequeo de duplicado corriera antes que la validación de
    # campos, un payload basura devolvería 409 y el cliente nunca se enteraría
    # de que además mandó un rating inválido. El 400 tiene que ganar.
    booking = _booking(Booking.Status.COMPLETED, cliente_user)
    Review.objects.create(booking=booking, rating=5, comment="Buena")

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(URL, {"booking": booking.id, "rating": 9})

    data = response.json()
    assert response.status_code == 400
    assert data["code"] == "validation_error"
    assert "rating" in data["details"]


# --- Carrera: el candado del serializer no se entera ---------------------


def test_carrera_review_duplicada_da_409(
    api_client, cliente_user, _booking, monkeypatch
):
    # Simulamos la ventana TOCTOU: _ya_tiene_review devuelve False (como si
    # la otra review se hubiera insertado justo después del chequeo), así que
    # el 409 solo puede salir del IntegrityError + recheck de la view.
    from bookings.serializers import ReviewCreateSerializer

    booking = _booking(Booking.Status.COMPLETED, cliente_user)
    Review.objects.create(booking=booking, rating=5, comment="Buena")
    monkeypatch.setattr(
        ReviewCreateSerializer, "_ya_tiene_review", lambda self, booking: False
    )

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(URL, {"booking": booking.id, "rating": 3})

    data = response.json()
    assert response.status_code == 409
    assert data["code"] == "duplicate_review"
    assert Review.objects.filter(booking=booking).count() == 1


def test_integrity_error_ajeno_no_se_disfraza_de_duplicado(
    api_client, cliente_user, _booking, monkeypatch
):
    # ATAQUE al except: si capturara cualquier IntegrityError, un bug real
    # (otra constraint) saldría como 409 "ya existe una reseña" y nadie se
    # enteraría. Sin review previa, el recheck da False y se re-lanza.
    from bookings.serializers import ReviewCreateSerializer

    booking = _booking(Booking.Status.COMPLETED, cliente_user)

    def _explota(self, **kwargs):
        raise IntegrityError("otra cosa")

    monkeypatch.setattr(ReviewCreateSerializer, "save", _explota)

    api_client.force_authenticate(user=cliente_user)
    with pytest.raises(IntegrityError, match="otra cosa"):
        api_client.post(URL, {"booking": booking.id, "rating": 3})
