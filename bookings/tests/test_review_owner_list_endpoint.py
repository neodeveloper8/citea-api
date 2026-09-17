from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from bookings.models import Booking, Review, ReviewResponse
from businesses.models import Business, Category, Service
from users.models import User

pytestmark = pytest.mark.django_db

LIMA_TZ = ZoneInfo("America/Lima")


def _aware(hora):
    fecha = date.today() + timedelta(days=1)
    return datetime.combine(fecha, hora, tzinfo=LIMA_TZ)


def _business_reviews_url(business):
    return f"/api/reviews/business/{business.slug}/"


@pytest.fixture
def category(db):
    return Category.objects.create(name="Peluquería Test")


@pytest.fixture
def business(dueno_user, category):
    return Business.objects.create(
        owner=dueno_user,
        category=category,
        name="Salón Owner List",
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


def test_dueno_lista_las_reviews_de_su_negocio(
    api_client, dueno_user, cliente_user, business, _review
):
    review = _review(rating=4, comment="Muy bien")

    api_client.force_authenticate(user=dueno_user)
    response = api_client.get(_business_reviews_url(business))

    assert response.status_code == 200
    resultados = response.json()["results"]
    assert len(resultados) == 1
    data = resultados[0]
    assert data["id"] == review.id
    assert data["rating"] == 4
    assert data["comment"] == "Muy bien"
    assert data["customer_name"] == cliente_user.get_full_name()
    assert data["response"] is None  # sin respuesta todavía


def test_dueno_ve_la_respuesta_anidada_si_existe(
    api_client, dueno_user, business, _review
):
    review = _review()
    ReviewResponse.objects.create(review=review, body="Gracias por tu visita")

    api_client.force_authenticate(user=dueno_user)
    response = api_client.get(_business_reviews_url(business))

    assert response.status_code == 200
    data = response.json()["results"][0]
    assert data["response"]["body"] == "Gracias por tu visita"


# --- Permisos ---------------------------------------------------------


def test_cliente_autenticado_da_403(api_client, cliente_user, business, _review):
    _review()

    api_client.force_authenticate(user=cliente_user)
    response = api_client.get(_business_reviews_url(business))

    assert response.status_code == 403


def test_dueno_ajeno_ve_lista_vacia_no_404(api_client, otro_dueno, business, _review):
    """El negocio no es de otro_dueno -> el queryset sale vacío, NO 404."""
    _review()

    api_client.force_authenticate(user=otro_dueno)
    response = api_client.get(_business_reviews_url(business))

    assert response.status_code == 200
    assert response.json()["results"] == []


def test_slug_inexistente_da_lista_vacia_no_404(api_client, dueno_user):
    api_client.force_authenticate(user=dueno_user)
    response = api_client.get("/api/reviews/business/no-existe-este-slug/")

    assert response.status_code == 200
    assert response.json()["results"] == []


def test_sin_autenticacion_da_401(api_client, business, _review):
    _review()

    response = api_client.get(_business_reviews_url(business))

    assert response.status_code == 401
