from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from bookings.models import Booking
from businesses.models import Business, Category, Service
from users.models import User

pytestmark = pytest.mark.django_db

LIMA_TZ = ZoneInfo("America/Lima")

ME_URL = "/api/bookings/me/"


def _aware_lima(fecha, hora):
    return datetime.combine(fecha, hora, tzinfo=LIMA_TZ)


def _business_url(business):
    return f"/api/bookings/business/{business.slug}/"


def _crear_booking(customer, business, service, inicio, fin, status):
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


@pytest.fixture
def cliente_a(db):
    return User.objects.create_user(
        email="cliente-a@test.pe",
        password="ClaveTest123",
        phone="900000001",
    )


@pytest.fixture
def cliente_b(db):
    return User.objects.create_user(
        email="cliente-b@test.pe",
        password="ClaveTest123",
        phone="900000002",
    )


@pytest.fixture
def dueno_a(db):
    return User.objects.create_user(
        email="dueno-a@test.pe",
        password="ClaveTest123",
        role=User.Role.DUENO,
    )


@pytest.fixture
def dueno_b(db):
    return User.objects.create_user(
        email="dueno-b@test.pe",
        password="ClaveTest123",
        role=User.Role.DUENO,
    )


@pytest.fixture
def category(db):
    return Category.objects.create(name="Peluquería Test")


@pytest.fixture
def business(dueno_a, category):
    return Business.objects.create(
        owner=dueno_a,
        category=category,
        name="Salón Lectura",
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


@pytest.fixture
def escenario(cliente_a, cliente_b, dueno_a, dueno_b, business, service):
    fecha_1 = date.today() + timedelta(days=1)
    fecha_2 = date.today() + timedelta(days=2)
    fecha_5 = date.today() + timedelta(days=5)

    # cliente_a: pending, confirmed, y una pending lejos en el tiempo.
    a1 = _crear_booking(
        cliente_a,
        business,
        service,
        _aware_lima(fecha_1, time(10, 0)),
        _aware_lima(fecha_1, time(10, 30)),
        Booking.Status.PENDING,
    )
    a2 = _crear_booking(
        cliente_a,
        business,
        service,
        _aware_lima(fecha_2, time(11, 0)),
        _aware_lima(fecha_2, time(11, 30)),
        Booking.Status.CONFIRMED,
    )
    a3 = _crear_booking(
        cliente_a,
        business,
        service,
        _aware_lima(fecha_5, time(9, 0)),
        _aware_lima(fecha_5, time(9, 30)),
        Booking.Status.PENDING,
    )
    # cliente_b: misma negocio, mismo día que a1 pero otro horario (no solapa).
    b1 = _crear_booking(
        cliente_b,
        business,
        service,
        _aware_lima(fecha_1, time(12, 0)),
        _aware_lima(fecha_1, time(12, 30)),
        Booking.Status.PENDING,
    )

    return {
        "cliente_a": cliente_a,
        "cliente_b": cliente_b,
        "dueno_a": dueno_a,
        "dueno_b": dueno_b,
        "business": business,
        "service": service,
        "a1": a1,
        "a2": a2,
        "a3": a3,
        "b1": b1,
        "fecha_1": fecha_1,
        "fecha_2": fecha_2,
        "fecha_5": fecha_5,
    }


# --- GET /api/bookings/me/ ---------------------------------------------


def test_me_solo_devuelve_reservas_propias(api_client, escenario):
    api_client.force_authenticate(user=escenario["cliente_a"])
    response = api_client.get(ME_URL)

    assert response.status_code == 200
    ids = {b["id"] for b in response.json()["results"]}
    assert ids == {escenario["a1"].id, escenario["a2"].id, escenario["a3"].id}
    assert escenario["b1"].id not in ids


def test_me_sin_autenticacion_da_401(api_client):
    response = api_client.get(ME_URL)
    assert response.status_code == 401


def test_me_forma_de_la_respuesta(api_client, escenario):
    api_client.force_authenticate(user=escenario["cliente_a"])
    response = api_client.get(ME_URL)

    assert response.status_code == 200
    primero = response.json()["results"][0]
    assert set(primero["business"].keys()) == {"slug", "name"}
    assert primero["business"]["slug"] == escenario["business"].slug
    assert primero["business"]["name"] == escenario["business"].name
    assert set(primero["service"].keys()) == {"id", "name", "duration_minutes"}
    assert primero["service"]["name"] == escenario["service"].name
    assert (
        primero["service"]["duration_minutes"] == escenario["service"].duration_minutes
    )
    assert "status" in primero


def test_me_filtro_status_pending(api_client, escenario):
    api_client.force_authenticate(user=escenario["cliente_a"])
    response = api_client.get(ME_URL, {"status": "pending"})

    assert response.status_code == 200
    ids = {b["id"] for b in response.json()["results"]}
    assert ids == {escenario["a1"].id, escenario["a3"].id}


def test_me_filtro_date_from_date_to(api_client, escenario):
    api_client.force_authenticate(user=escenario["cliente_a"])
    response = api_client.get(
        ME_URL,
        {
            "date_from": escenario["fecha_1"].isoformat(),
            "date_to": escenario["fecha_2"].isoformat(),
        },
    )

    assert response.status_code == 200
    ids = {b["id"] for b in response.json()["results"]}
    assert ids == {escenario["a1"].id, escenario["a2"].id}


def test_me_orden_ascendente_por_start_datetime(api_client, escenario):
    api_client.force_authenticate(user=escenario["cliente_a"])
    response = api_client.get(ME_URL)

    assert response.status_code == 200
    resultados = response.json()["results"]
    inicios = [b["start_datetime"] for b in resultados]
    assert inicios == sorted(inicios)


# --- GET /api/bookings/business/<slug>/ ---------------------------------


def test_business_dueno_ve_reservas_de_su_negocio(api_client, escenario):
    api_client.force_authenticate(user=escenario["dueno_a"])
    response = api_client.get(_business_url(escenario["business"]))

    assert response.status_code == 200
    ids = {b["id"] for b in response.json()["results"]}
    assert ids == {
        escenario["a1"].id,
        escenario["a2"].id,
        escenario["a3"].id,
        escenario["b1"].id,
    }


def test_business_incluye_contacto_del_cliente(api_client, escenario):
    api_client.force_authenticate(user=escenario["dueno_a"])
    response = api_client.get(_business_url(escenario["business"]))

    assert response.status_code == 200
    por_id = {b["id"]: b for b in response.json()["results"]}
    customer_a1 = por_id[escenario["a1"].id]["customer"]
    assert customer_a1["email"] == escenario["cliente_a"].email
    assert customer_a1["phone"] == escenario["cliente_a"].phone


def test_business_otro_dueno_da_404(api_client, escenario):
    api_client.force_authenticate(user=escenario["dueno_b"])
    response = api_client.get(_business_url(escenario["business"]))

    assert response.status_code == 404


def test_business_cliente_no_dueno_da_403(api_client, escenario):
    api_client.force_authenticate(user=escenario["cliente_a"])
    response = api_client.get(_business_url(escenario["business"]))

    assert response.status_code == 403


def test_business_slug_inexistente_da_404(api_client, escenario):
    api_client.force_authenticate(user=escenario["dueno_a"])
    response = api_client.get("/api/bookings/business/no-existe-este-slug/")

    assert response.status_code == 404


def test_business_sin_autenticacion_da_401(api_client, escenario):
    response = api_client.get(_business_url(escenario["business"]))
    assert response.status_code == 401


def test_business_filtro_status_confirmed(api_client, escenario):
    api_client.force_authenticate(user=escenario["dueno_a"])
    response = api_client.get(
        _business_url(escenario["business"]), {"status": "confirmed"}
    )

    assert response.status_code == 200
    ids = {b["id"] for b in response.json()["results"]}
    assert ids == {escenario["a2"].id}
