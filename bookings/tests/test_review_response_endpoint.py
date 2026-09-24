from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.db import IntegrityError, transaction

from bookings.models import Booking, Review, ReviewResponse
from businesses.models import Business, Category, Service
from users.models import User

pytestmark = pytest.mark.django_db

LIMA_TZ = ZoneInfo("America/Lima")

URL = "/api/review-responses/"


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
        name="Salón Responses",
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
def _review(business, service, cliente_user):
    def crear(rating=5, comment="Buena atención"):
        inicio = _aware(time(11, 0))
        fin = _aware(time(11, 30))
        booking = Booking.objects.create(
            customer=cliente_user,
            business=business,
            service=service,
            start_datetime=inicio,
            end_datetime=fin,
            price_at_booking=service.price,
            duration_at_booking=service.duration_minutes,
            status=Booking.Status.COMPLETED,
        )
        return Review.objects.create(booking=booking, rating=rating, comment=comment)

    return crear


# --- Camino feliz -----------------------------------------------------


def test_dueno_responde_review_de_su_negocio_devuelve_201(
    api_client, dueno_user, _review
):
    review = _review()

    api_client.force_authenticate(user=dueno_user)
    response = api_client.post(URL, {"review": review.id, "body": "¡Gracias!"})

    assert response.status_code == 201
    data = response.json()
    assert "created_at" in data  # confirma que responde con el ReadSerializer

    resp = ReviewResponse.objects.get(review=review)
    assert resp.body == "¡Gracias!"


# --- Permisos ---------------------------------------------------------


def test_cliente_autenticado_da_403(api_client, cliente_user, _review):
    review = _review()

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(URL, {"review": review.id, "body": "¡Gracias!"})

    assert response.status_code == 403
    assert not ReviewResponse.objects.filter(review=review).exists()


def test_dueno_ajeno_responde_review_de_otro_negocio_da_400(
    api_client, otro_dueno, _review
):
    review = _review()

    api_client.force_authenticate(user=otro_dueno)
    response = api_client.post(URL, {"review": review.id, "body": "¡Gracias!"})

    assert response.status_code == 400
    assert not ReviewResponse.objects.filter(review=review).exists()


# --- Ya respondida ------------------------------------------------------


def test_review_ya_respondida_da_409(api_client, dueno_user, _review):
    review = _review()

    api_client.force_authenticate(user=dueno_user)
    primera = api_client.post(URL, {"review": review.id, "body": "¡Gracias!"})
    assert primera.status_code == 201

    segunda = api_client.post(URL, {"review": review.id, "body": "Otra respuesta"})

    data = segunda.json()
    assert segunda.status_code == 409
    assert data["code"] == "duplicate_response"
    assert data["details"] == {}
    assert ReviewResponse.objects.filter(review=review).count() == 1


def test_segunda_review_response_mismo_review_levanta_integrity_error(_review):
    review = _review()
    ReviewResponse.objects.create(review=review, body="Primera")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ReviewResponse.objects.create(review=review, body="Segunda")


# --- Sin autenticación -----------------------------------------------


def test_sin_autenticacion_da_401(api_client, _review):
    review = _review()

    response = api_client.post(URL, {"review": review.id, "body": "¡Gracias!"})

    assert response.status_code == 401


# --- Precedencia: un 409 no puede tapar un 400 ---------------------------


def test_respuesta_duplicada_con_body_invalido_da_400_no_409(
    api_client, dueno_user, _review
):
    # ATAQUE: el chequeo de duplicado corre en validate(), o sea DESPUÉS de
    # la validación de campos. Un body vacío tiene que ganarle al 409.
    review = _review()
    ReviewResponse.objects.create(review=review, body="Primera")

    api_client.force_authenticate(user=dueno_user)
    response = api_client.post(URL, {"review": review.id, "body": ""})

    data = response.json()
    assert response.status_code == 400
    assert data["code"] == "validation_error"
    assert "body" in data["details"]


# --- Carrera: el candado del serializer no se entera ---------------------


def test_carrera_respuesta_duplicada_da_409(
    api_client, dueno_user, _review, monkeypatch
):
    from bookings.serializers import ReviewResponseCreateSerializer

    review = _review()
    ReviewResponse.objects.create(review=review, body="Primera")
    monkeypatch.setattr(
        ReviewResponseCreateSerializer,
        "_ya_tiene_respuesta",
        lambda self, review: False,
    )

    api_client.force_authenticate(user=dueno_user)
    response = api_client.post(URL, {"review": review.id, "body": "Segunda"})

    data = response.json()
    assert response.status_code == 409
    assert data["code"] == "duplicate_response"
    assert ReviewResponse.objects.filter(review=review).count() == 1


def test_integrity_error_ajeno_no_se_disfraza_de_duplicado(
    api_client, dueno_user, _review, monkeypatch
):
    from bookings.serializers import ReviewResponseCreateSerializer

    review = _review()

    def _explota(self, **kwargs):
        raise IntegrityError("otra cosa")

    monkeypatch.setattr(ReviewResponseCreateSerializer, "save", _explota)

    api_client.force_authenticate(user=dueno_user)
    with pytest.raises(IntegrityError, match="otra cosa"):
        api_client.post(URL, {"review": review.id, "body": "Hola"})
