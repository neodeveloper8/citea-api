from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from bookings.models import Booking, Review, ReviewResponse
from businesses.models import Business, Category, Service
from users.models import User

pytestmark = pytest.mark.django_db

LIMA_TZ = ZoneInfo("America/Lima")


def _aware(hora, dias=1):
    fecha = date.today() + timedelta(days=dias)
    return datetime.combine(fecha, hora, tzinfo=LIMA_TZ)


def _detail_url(business):
    return f"/api/businesses/{business.slug}/"


@pytest.fixture
def dueno(db):
    return User.objects.create_user(
        email="dueno-reviews@test.pe", password="ClaveTest123", role=User.Role.DUENO
    )


@pytest.fixture
def category(db):
    return Category.objects.create(name="Peluquería Test")


@pytest.fixture
def business(dueno, category):
    return Business.objects.create(
        owner=dueno,
        category=category,
        name="Salón Detalle Reviews",
        status=Business.Status.APPROVED,
    )


@pytest.fixture
def service(business):
    return Service.objects.create(
        business=business,
        name="Corte",
        duration_minutes=30,
        price="20.00",
    )


def _cliente(email, full_name=""):
    return User.objects.create_user(
        email=email, password="ClaveTest123", full_name=full_name
    )


def _review_completada(business, service, customer, rating, comment="", dias=1):
    inicio = _aware(time(11, 0), dias=dias)
    fin = _aware(time(11, 30), dias=dias)
    booking = Booking.objects.create(
        customer=customer,
        business=business,
        service=service,
        start_datetime=inicio,
        end_datetime=fin,
        price_at_booking=service.price,
        duration_at_booking=service.duration_minutes,
        status=Booking.Status.COMPLETED,
    )
    return Review.objects.create(booking=booking, rating=rating, comment=comment)


# --- Sin reviews ----------------------------------------------------------


def test_negocio_sin_reviews(api_client, business):
    response = api_client.get(_detail_url(business))

    assert response.status_code == 200
    data = response.json()
    assert data["rating_avg"] is None
    assert data["rating_count"] == 0
    assert data["reviews"] == []


# --- Promedio con 2 reviews -------------------------------------------


def test_negocio_con_dos_reviews_promedio_4_5(api_client, business, service):
    cliente_a = _cliente("cliente-a@test.pe", "Cliente A")
    cliente_b = _cliente("cliente-b@test.pe", "Cliente B")
    _review_completada(business, service, cliente_a, rating=4, dias=1)
    _review_completada(business, service, cliente_b, rating=5, dias=2)

    response = api_client.get(_detail_url(business))

    assert response.status_code == 200
    data = response.json()
    assert data["rating_avg"] == 4.5
    assert data["rating_count"] == 2
    assert len(data["reviews"]) == 2


# --- Privacidad: forma del item de review -------------------------------


def test_review_item_no_expone_booking_ni_email_ni_phone(api_client, business, service):
    cliente = _cliente("privacidad@test.pe", "Juan Pérez")
    cliente.phone = "999888777"
    cliente.save()
    _review_completada(business, service, cliente, rating=5, comment="Genial")

    response = api_client.get(_detail_url(business))

    assert response.status_code == 200
    item = response.json()["reviews"][0]
    assert set(item.keys()) == {
        "id",
        "rating",
        "comment",
        "author",
        "created_at",
        "response",
    }
    assert "booking" not in item
    assert cliente.email not in str(item)
    assert cliente.phone not in str(item)


# --- author = get_short_name --------------------------------------------


def test_author_es_el_primer_nombre_del_cliente(api_client, business, service):
    cliente = _cliente("juan@test.pe", "Juan Pérez")
    _review_completada(business, service, cliente, rating=5)

    response = api_client.get(_detail_url(business))

    assert response.status_code == 200
    item = response.json()["reviews"][0]
    assert item["author"] == "Juan"


# --- Review con respuesta del dueño --------------------------------------


def test_review_con_respuesta_trae_response_no_null(api_client, business, service):
    cliente = _cliente("respondida@test.pe", "Ana Torres")
    review = _review_completada(business, service, cliente, rating=5)
    ReviewResponse.objects.create(review=review, body="¡Gracias por tu visita!")

    response = api_client.get(_detail_url(business))

    assert response.status_code == 200
    item = response.json()["reviews"][0]
    assert item["response"] is not None
    assert item["response"]["body"] == "¡Gracias por tu visita!"


# --- Público, sin autenticación -----------------------------------------


def test_endpoint_es_publico_sin_autenticacion(api_client, business, service):
    cliente = _cliente("publico@test.pe", "Publico Test")
    _review_completada(business, service, cliente, rating=5)

    # api_client sin force_authenticate: request anónimo.
    response = api_client.get(_detail_url(business))

    assert response.status_code == 200
    assert len(response.json()["reviews"]) == 1


# --- Redondeo a 1 decimal ------------------------------------------------


def test_rating_avg_redondea_a_un_decimal(api_client, business, service):
    cliente_a = _cliente("r1@test.pe", "Cliente Uno")
    cliente_b = _cliente("r2@test.pe", "Cliente Dos")
    cliente_c = _cliente("r3@test.pe", "Cliente Tres")
    _review_completada(business, service, cliente_a, rating=5, dias=1)
    _review_completada(business, service, cliente_b, rating=4, dias=2)
    _review_completada(business, service, cliente_c, rating=4, dias=3)

    response = api_client.get(_detail_url(business))

    assert response.status_code == 200
    assert response.json()["rating_avg"] == 4.3
