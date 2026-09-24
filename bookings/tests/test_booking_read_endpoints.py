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


def test_business_incluye_full_name_del_cliente(api_client, escenario):
    cliente_a = escenario["cliente_a"]
    cliente_a.full_name = "Cliente Nombre"
    cliente_a.save()

    api_client.force_authenticate(user=escenario["dueno_a"])
    response = api_client.get(_business_url(escenario["business"]))

    assert response.status_code == 200
    por_id = {b["id"]: b for b in response.json()["results"]}
    customer_a1 = por_id[escenario["a1"].id]["customer"]
    assert customer_a1["full_name"] == "Cliente Nombre"


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


# --- Contrato de error en los 404 ---------------------------------------
# Esta view llega al 404 por dos caminos distintos y los dos levantan la
# Http404 de Django, que no tiene default_code. Antes del saneamiento salían
# con code "error"; acá se fija que salgan con "not_found".


def test_business_slug_inexistente_respeta_el_contrato_de_error(api_client, escenario):
    # Camino get_object_or_404 de django.shortcuts.
    api_client.force_authenticate(user=escenario["dueno_a"])
    response = api_client.get("/api/bookings/business/no-existe-este-slug/")

    data = response.json()
    assert response.status_code == 404
    assert data["code"] == "not_found"
    assert set(data.keys()) == {"error", "code", "details"}
    assert data["details"] == {}


def test_business_de_otro_dueno_respeta_el_contrato_de_error(api_client, escenario):
    # Camino raise Http404() explícito: se responde 404 (no 403) para no
    # confirmarle a un no-dueño que el negocio existe.
    api_client.force_authenticate(user=escenario["dueno_b"])
    response = api_client.get(_business_url(escenario["business"]))

    data = response.json()
    assert response.status_code == 404
    assert data["code"] == "not_found"
    assert set(data.keys()) == {"error", "code", "details"}
    # El slug del negocio ajeno no se filtra en el mensaje.
    assert escenario["business"].slug not in data["error"]


# --- Filtro de fechas: bordes de zona horaria ----------------------------
# Las reservas se guardan en UTC, pero date_from/date_to son fechas que el
# usuario piensa en hora de Lima. Una reserva de las 23:30 de Lima cae al día
# SIGUIENTE en UTC, así que un filtro que compare contra UTC la dejaría
# afuera de su propio día. Estos tests fijan la semántica en hora local.


@pytest.fixture
def bordes_tz(escenario):
    """Reservas en los bordes del día, en hora de Lima.

    fecha_1 23:30 Lima = fecha_2 04:30 UTC (cruza el día en UTC).
    fecha_2 00:00 Lima = fecha_2 05:00 UTC (primer instante del día local).
    """
    tarde = _crear_booking(
        escenario["cliente_a"],
        escenario["business"],
        escenario["service"],
        _aware_lima(escenario["fecha_1"], time(23, 30)),
        _aware_lima(escenario["fecha_2"], time(0, 0)),
        Booking.Status.PENDING,
    )
    medianoche = _crear_booking(
        escenario["cliente_a"],
        escenario["business"],
        escenario["service"],
        _aware_lima(escenario["fecha_2"], time(0, 0)),
        _aware_lima(escenario["fecha_2"], time(0, 30)),
        Booking.Status.PENDING,
    )
    return {"tarde": tarde, "medianoche": medianoche}


# Los dos endpoints que pasan por BookingFilter. export_clients NO lo usa.
ENDPOINTS = ["me", "business"]


def _url_y_actor(nombre, escenario):
    if nombre == "me":
        return ME_URL, escenario["cliente_a"]
    return _business_url(escenario["business"]), escenario["dueno_a"]


def _ids_filtrados(api_client, escenario, endpoint, **params):
    url, actor = _url_y_actor(endpoint, escenario)
    api_client.force_authenticate(user=actor)
    response = api_client.get(url, params)
    assert response.status_code == 200
    return {b["id"] for b in response.json()["results"]}


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_date_to_incluye_reserva_de_las_2330_del_mismo_dia(
    api_client, escenario, bordes_tz, endpoint
):
    # REGRESIÓN del bug clásico: 23:30 Lima es 04:30 UTC del día siguiente.
    ids = _ids_filtrados(
        api_client, escenario, endpoint, date_to=escenario["fecha_1"].isoformat()
    )

    assert bordes_tz["tarde"].id in ids


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_date_to_del_dia_anterior_excluye_la_de_las_2330(
    api_client, escenario, bordes_tz, endpoint
):
    ayer = escenario["fecha_1"] - timedelta(days=1)

    ids = _ids_filtrados(api_client, escenario, endpoint, date_to=ayer.isoformat())

    assert bordes_tz["tarde"].id not in ids


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_date_from_del_dia_siguiente_excluye_la_de_las_2330(
    api_client, escenario, bordes_tz, endpoint
):
    ids = _ids_filtrados(
        api_client, escenario, endpoint, date_from=escenario["fecha_2"].isoformat()
    )

    assert bordes_tz["tarde"].id not in ids


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_date_from_del_mismo_dia_incluye_la_de_las_2330(
    api_client, escenario, bordes_tz, endpoint
):
    ids = _ids_filtrados(
        api_client, escenario, endpoint, date_from=escenario["fecha_1"].isoformat()
    )

    assert bordes_tz["tarde"].id in ids


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_medianoche_local_pertenece_a_su_propio_dia(
    api_client, escenario, bordes_tz, endpoint
):
    # 00:00 de fecha_2 es el PRIMER instante de fecha_2: no puede contar
    # como fecha_1 (el límite inferior tiene que ser inclusivo).
    ids_dia_previo = _ids_filtrados(
        api_client, escenario, endpoint, date_to=escenario["fecha_1"].isoformat()
    )
    ids_su_dia = _ids_filtrados(
        api_client, escenario, endpoint, date_from=escenario["fecha_2"].isoformat()
    )

    assert bordes_tz["medianoche"].id not in ids_dia_previo
    assert bordes_tz["medianoche"].id in ids_su_dia


def test_date_from_igual_date_to_devuelve_solo_ese_dia(api_client, escenario):
    # escenario tiene reservas de cliente_a en fecha_1 (a1), fecha_2 (a2) y
    # fecha_5 (a3): hay días antes y después del pedido.
    ids = _ids_filtrados(
        api_client,
        escenario,
        "me",
        date_from=escenario["fecha_2"].isoformat(),
        date_to=escenario["fecha_2"].isoformat(),
    )

    assert ids == {escenario["a2"].id}


def test_rango_invertido_devuelve_vacio_sin_error(api_client, escenario):
    # date_from > date_to no es un error de validación: es un rango vacío.
    ids = _ids_filtrados(
        api_client,
        escenario,
        "me",
        date_from=escenario["fecha_5"].isoformat(),
        date_to=escenario["fecha_1"].isoformat(),
    )

    assert ids == set()
