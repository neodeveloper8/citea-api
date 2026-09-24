"""El cuerpo de POST/PATCH de Business tiene que ser el mismo que el del GET
de detalle.

Si difieren, el frontend necesita dos parsers para el mismo recurso y, peor,
después de crear o editar no puede pintar la pantalla de detalle con lo que
recibió: tiene que hacer un GET extra.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from bookings.models import Booking, Review
from businesses.models import Business, Category, Service
from users.models import User

pytestmark = pytest.mark.django_db

LIMA_TZ = ZoneInfo("America/Lima")

LIST_URL = "/api/businesses/"


def _detail_url(slug):
    return f"/api/businesses/{slug}/"


@pytest.fixture
def dueno(db):
    return User.objects.create_user(
        email="dueno-write@test.pe", password="ClaveTest123", role=User.Role.DUENO
    )


@pytest.fixture
def category(db):
    return Category.objects.create(name="Peluquería Write")


@pytest.fixture
def otra_category(db):
    return Category.objects.create(name="Barbería Write")


@pytest.fixture
def business(dueno, category):
    return Business.objects.create(
        owner=dueno,
        category=category,
        name="Salón Write",
        status=Business.Status.APPROVED,
    )


def _payload(category, **extra):
    body = {
        "name": "Salón Nuevo",
        "category": category.id,
        "address": "Av. Siempre Viva 742",
        "description": "Un salón",
    }
    body.update(extra)
    return body


# --- Paridad POST/PATCH vs GET de detalle --------------------------------


def test_post_responde_igual_que_el_get_de_detalle(api_client, dueno, category):
    api_client.force_authenticate(user=dueno)

    post = api_client.post(LIST_URL, _payload(category), format="json")
    assert post.status_code == 201

    get = api_client.get(_detail_url(post.json()["slug"]))
    assert get.status_code == 200

    assert post.json() == get.json()


def test_patch_responde_igual_que_el_get_de_detalle(api_client, dueno, business):
    api_client.force_authenticate(user=dueno)

    patch = api_client.patch(
        _detail_url(business.slug), {"name": "Salón Renombrado"}, format="json"
    )
    assert patch.status_code == 200

    get = api_client.get(_detail_url(business.slug))
    assert get.status_code == 200

    assert patch.json() == get.json()


# --- La respuesta refleja el estado NUEVO, no uno cacheado ---------------


def test_patch_de_categoria_devuelve_la_categoria_nueva_anidada(
    api_client, dueno, business, category, otra_category
):
    api_client.force_authenticate(user=dueno)

    response = api_client.patch(
        _detail_url(business.slug), {"category": otra_category.id}, format="json"
    )

    data = response.json()
    assert response.status_code == 200
    # Anidada, no un PK: es el shape del serializer de detalle.
    assert data["category"]["id"] == otra_category.id
    assert data["category"]["name"] == otra_category.name
    assert data["category"]["slug"] == otra_category.slug


def test_patch_de_negocio_con_reviews_devuelve_el_rating_real(
    api_client, dueno, business, category
):
    # Las anotaciones de rating viven en el queryset de detalle. Si la
    # respuesta serializara la instancia devuelta por save() en vez de
    # releerla, los getattr caerían a sus defaults y el rating saldría
    # null/0 aunque el negocio tenga reseñas.
    cliente = User.objects.create_user(email="cli-write@test.pe", password="x")
    service = Service.objects.create(
        business=business, name="Corte", duration_minutes=30, price="20.00"
    )
    inicio = datetime.combine(
        date.today() + timedelta(days=1), time(10, 0), tzinfo=LIMA_TZ
    )
    booking = Booking.objects.create(
        customer=cliente,
        business=business,
        service=service,
        start_datetime=inicio,
        end_datetime=inicio + timedelta(minutes=30),
        price_at_booking=service.price,
        duration_at_booking=service.duration_minutes,
        status=Booking.Status.COMPLETED,
    )
    Review.objects.create(booking=booking, rating=4, comment="Buena")

    api_client.force_authenticate(user=dueno)
    response = api_client.patch(
        _detail_url(business.slug), {"name": "Con Reviews"}, format="json"
    )

    data = response.json()
    assert response.status_code == 200
    assert data["rating_avg"] == 4.0
    assert data["rating_count"] == 1
    assert len(data["reviews"]) == 1


def test_post_sin_reviews_devuelve_rating_avg_null(api_client, dueno, category):
    # Decisión 53: sin reseñas el promedio es null, NO 0. Un 0 se leería como
    # "lo calificaron con cero", que es una afirmación distinta a "no hay
    # datos". El contador sí es 0, porque contar cero reseñas ES cero.
    api_client.force_authenticate(user=dueno)

    response = api_client.post(LIST_URL, _payload(category), format="json")

    data = response.json()
    assert response.status_code == 201
    assert data["rating_avg"] is None
    assert data["rating_count"] == 0
    assert data["reviews"] == []


# --- Mass assignment ------------------------------------------------------


def test_owner_y_status_del_body_se_ignoran(api_client, dueno, category):
    # REGRESIÓN: owner lo pone perform_create desde request.user, y status no
    # está en el serializer de escritura, así que usa el default del modelo.
    # Un dueño no puede auto-aprobarse el negocio ni crearlo a nombre de otro.
    otro = User.objects.create_user(
        email="otro-write@test.pe", password="x", role=User.Role.DUENO
    )
    api_client.force_authenticate(user=dueno)

    response = api_client.post(
        LIST_URL,
        _payload(category, owner=otro.id, status=Business.Status.APPROVED),
        format="json",
    )

    assert response.status_code == 201
    creado = Business.objects.get(slug=response.json()["slug"])
    assert creado.owner == dueno
    assert creado.status == Business.Status.DRAFT
