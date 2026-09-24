"""Contrato de ESCRITURA de Business: forma de la respuesta, permisos y
campos de autoridad.

Dos bloques:

- Paridad de cuerpos: POST/PATCH tienen que responder lo mismo que el GET de
  detalle. Si difieren, el frontend necesita dos parsers para el mismo recurso
  y, después de crear o editar, un GET extra para pintar el detalle.
- Permisos y campos de autoridad: quién puede escribir, qué status devuelve
  cada intento fallido, y qué campos NO puede fijar el cliente aunque los
  mande (owner, status, slug). DRF los ignora en silencio, así que estos
  tests verifican en la BD, no en la respuesta.
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
def otro_dueno(db):
    return User.objects.create_user(
        email="otro-dueno-write@test.pe", password="ClaveTest123", role=User.Role.DUENO
    )


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


def test_owner_y_status_del_body_se_ignoran(api_client, dueno, category, otro_dueno):
    # REGRESIÓN: owner lo pone perform_create desde request.user, y status no
    # está en el serializer de escritura, así que usa el default del modelo.
    # Un dueño no puede auto-aprobarse el negocio ni crearlo a nombre de otro.
    api_client.force_authenticate(user=dueno)

    response = api_client.post(
        LIST_URL,
        _payload(category, owner=otro_dueno.id, status=Business.Status.APPROVED),
        format="json",
    )

    assert response.status_code == 201
    creado = Business.objects.get(slug=response.json()["slug"])
    assert creado.owner == dueno
    assert creado.status == Business.Status.DRAFT


# --- POST: permisos -------------------------------------------------------


def test_post_sin_autenticar_da_401(api_client, category):
    response = api_client.post(LIST_URL, _payload(category), format="json")

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
    assert not Business.objects.exists()


def test_post_como_cliente_da_403(api_client, cliente_user, category):
    # IsDueno.has_permission corta en check_permissions(), antes del handler.
    api_client.force_authenticate(user=cliente_user)

    response = api_client.post(LIST_URL, _payload(category), format="json")

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
    assert not Business.objects.exists()


def test_post_con_category_inexistente_da_400(api_client, dueno, category):
    # _payload toma la category posicional, así que el id inexistente se pisa
    # después (pasarlo por **extra choca con el parámetro).
    payload = _payload(category)
    payload["category"] = category.id + 9999

    api_client.force_authenticate(user=dueno)
    response = api_client.post(LIST_URL, payload, format="json")

    data = response.json()
    assert response.status_code == 400
    assert data["code"] == "validation_error"
    assert "category" in data["details"]
    assert not Business.objects.exists()


# --- PATCH: permisos ------------------------------------------------------


def test_patch_de_otro_dueno_da_404_y_no_modifica_nada(
    api_client, business, otro_dueno
):
    # 404 y NO 403: el queryset de update filtra owner=user, así que para el
    # dueño ajeno el negocio no existe. Un 403 le confirmaría que el slug
    # corresponde a un negocio real.
    original_name = business.name
    api_client.force_authenticate(user=otro_dueno)

    response = api_client.patch(
        _detail_url(business.slug), {"name": "Secuestrado"}, format="json"
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    business.refresh_from_db()
    assert business.name == original_name


def test_patch_como_cliente_da_403(api_client, business, cliente_user):
    # 403 (no 404) porque IsDueno.has_permission corre en check_permissions(),
    # ANTES del handler: el queryset filtrado por owner nunca llega a
    # ejecutarse. El rol se rechaza sin mirar de quién es el negocio.
    original_name = business.name
    api_client.force_authenticate(user=cliente_user)

    response = api_client.patch(
        _detail_url(business.slug), {"name": "Secuestrado"}, format="json"
    )

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
    business.refresh_from_db()
    assert business.name == original_name


def test_patch_sin_autenticar_da_401(api_client, business):
    original_name = business.name

    response = api_client.patch(
        _detail_url(business.slug), {"name": "Secuestrado"}, format="json"
    )

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
    business.refresh_from_db()
    assert business.name == original_name


# --- PATCH: campos de autoridad ------------------------------------------


def test_patch_de_name_no_cambia_el_slug(api_client, dueno, business):
    # Decisión 27: el slug se congela al crear. Si siguiera al nombre, cada
    # rename rompería los links ya compartidos del negocio.
    slug_original = business.slug

    api_client.force_authenticate(user=dueno)
    response = api_client.patch(
        _detail_url(business.slug), {"name": "Salón Con Otro Nombre"}, format="json"
    )

    assert response.status_code == 200
    assert response.json()["slug"] == slug_original
    business.refresh_from_db()
    assert business.slug == slug_original
    assert business.name == "Salón Con Otro Nombre"


def test_patch_no_permite_fijar_owner_status_ni_slug(
    api_client, dueno, business, otro_dueno
):
    # ATAQUE de mass assignment. DRF descarta los campos que no están en el
    # serializer SIN avisar, así que la respuesta 200 no prueba nada: hay que
    # mirar la BD.
    owner_original = business.owner
    status_original = business.status
    slug_original = business.slug

    api_client.force_authenticate(user=dueno)
    response = api_client.patch(
        _detail_url(business.slug),
        {
            "owner": otro_dueno.id,
            "status": Business.Status.APPROVED,
            "slug": "otro-slug",
        },
        format="json",
    )

    assert response.status_code == 200
    business.refresh_from_db()
    assert business.owner == owner_original
    assert business.status == status_original
    assert business.slug == slug_original
    # Y tampoco se colaron por la respuesta.
    assert response.json()["slug"] == slug_original


# --- DELETE no está expuesto ---------------------------------------------


def test_delete_de_negocio_propio_da_405(api_client, dueno, business):
    # El ViewSet no incluye DestroyModelMixin: el router no mapea DELETE.
    # Borrar un negocio arrastraría sus reservas (FK CASCADE), así que no se
    # expone.
    api_client.force_authenticate(user=dueno)

    response = api_client.delete(_detail_url(business.slug))

    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"
    assert Business.objects.filter(pk=business.pk).exists()
