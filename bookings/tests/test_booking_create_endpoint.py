from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils.dateparse import parse_datetime

from bookings.availability import Slot
from bookings.models import Booking
from businesses.models import Business, BusinessHours, Category, Service

pytestmark = pytest.mark.django_db

WEEKDAY_ABIERTO = 0  # lunes
LIMA_TZ = ZoneInfo("America/Lima")

URL = "/api/bookings/"


def _aware_lima(fecha, hora):
    return datetime.combine(fecha, hora, tzinfo=LIMA_TZ)


def _proxima_fecha_con_weekday(weekday, desde=None):
    """Primera fecha estrictamente futura (>= mañana) cuyo .weekday() == weekday."""
    base = desde or date.today()
    for delta in range(1, 8):
        candidata = base + timedelta(days=delta)
        if candidata.weekday() == weekday:
            return candidata
    raise AssertionError("No se encontró fecha con ese weekday.")


@pytest.fixture
def category(db):
    return Category.objects.create(name="Peluquería Test")


@pytest.fixture
def business(dueno_user, category):
    return Business.objects.create(
        owner=dueno_user,
        category=category,
        name="Salón Booking",
        status=Business.Status.APPROVED,
    )


@pytest.fixture
def business_hours(business):
    return BusinessHours.objects.create(
        business=business,
        weekday=WEEKDAY_ABIERTO,
        open_time=time(10, 0),
        close_time=time(18, 0),
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
def fecha_abierta(business_hours):
    return _proxima_fecha_con_weekday(WEEKDAY_ABIERTO)


def _payload(business, service, inicio):
    return {
        "business": business.id,
        "service": service.id,
        "start_datetime": inicio.isoformat(),
    }


def test_crear_booking_exitoso_devuelve_201(
    api_client, cliente_user, business, service, fecha_abierta
):
    inicio = _aware_lima(fecha_abierta, time(10, 0))
    fin_esperado = inicio + timedelta(minutes=service.duration_minutes)

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(URL, _payload(business, service, inicio))

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
    assert parse_datetime(data["end_datetime"]) == fin_esperado
    assert data["price_at_booking"] == "20.00"
    assert data["duration_at_booking"] == service.duration_minutes

    booking = Booking.objects.get(id=data["id"])
    assert booking.customer_id == cliente_user.id


def test_sin_autenticacion_da_401(api_client, business, service, fecha_abierta):
    inicio = _aware_lima(fecha_abierta, time(10, 0))

    response = api_client.post(URL, _payload(business, service, inicio))

    assert response.status_code == 401


def test_customer_del_body_se_ignora(
    api_client, cliente_user, dueno_user, business, service, fecha_abierta
):
    inicio = _aware_lima(fecha_abierta, time(10, 0))
    payload = _payload(business, service, inicio)
    payload["customer"] = dueno_user.id

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(URL, payload)

    assert response.status_code == 201
    booking = Booking.objects.get(id=response.json()["id"])
    assert booking.customer_id == cliente_user.id
    assert booking.customer_id != dueno_user.id


def test_slot_ocupado_da_409(
    api_client, cliente_user, business, service, fecha_abierta
):
    inicio = _aware_lima(fecha_abierta, time(10, 0))
    fin = inicio + timedelta(minutes=service.duration_minutes)
    Booking.objects.create(
        customer=cliente_user,
        business=business,
        service=service,
        start_datetime=inicio,
        end_datetime=fin,
        price_at_booking=service.price,
        duration_at_booking=service.duration_minutes,
        status=Booking.Status.PENDING,
    )

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(URL, _payload(business, service, inicio))

    # El horario SÍ está en la grilla: el pedido es válido y perdió contra
    # otra reserva. Mismo status y code que el camino de la carrera.
    data = response.json()
    assert response.status_code == 409
    assert data["code"] == "slot_taken"
    assert data["details"] == {}


def test_service_de_otro_negocio_da_400(
    api_client, cliente_user, business, service, fecha_abierta, dueno_user, category
):
    otro_negocio = Business.objects.create(
        owner=dueno_user,
        category=category,
        name="Otro Salón",
        status=Business.Status.APPROVED,
    )
    service_ajeno = Service.objects.create(
        business=otro_negocio,
        name="Corte ajeno",
        duration_minutes=30,
        price="15.00",
    )
    inicio = _aware_lima(fecha_abierta, time(10, 0))

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(URL, _payload(business, service_ajeno, inicio))

    assert response.status_code == 400


def test_business_en_draft_da_400(
    api_client, cliente_user, dueno_user, category, fecha_abierta
):
    negocio_draft = Business.objects.create(
        owner=dueno_user,
        category=category,
        name="Salón Borrador",
        status=Business.Status.DRAFT,
    )
    BusinessHours.objects.create(
        business=negocio_draft,
        weekday=WEEKDAY_ABIERTO,
        open_time=time(10, 0),
        close_time=time(18, 0),
    )
    service_draft = Service.objects.create(
        business=negocio_draft,
        name="Corte",
        duration_minutes=30,
        price="20.00",
    )
    inicio = _aware_lima(fecha_abierta, time(10, 0))

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(URL, _payload(negocio_draft, service_draft, inicio))

    assert response.status_code == 400


def test_horario_fuera_de_grilla_da_400(
    api_client, cliente_user, business, service, fecha_abierta
):
    # 10:07 no cae en ningún paso de 15 min, así que calcular_slots ni lo
    # emite: es un dato inválido (400), no un conflicto (409). El contraste
    # con test_slot_ocupado_da_409 es el punto de este test.
    inicio = _aware_lima(fecha_abierta, time(10, 7))

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(URL, _payload(business, service, inicio))

    data = response.json()
    assert response.status_code == 400
    assert data["code"] == "validation_error"
    assert "start_datetime" in data["details"]


def test_primer_booking_marca_is_first(
    api_client, cliente_user, business, service, fecha_abierta
):
    api_client.force_authenticate(user=cliente_user)

    inicio_1 = _aware_lima(fecha_abierta, time(10, 0))
    response_1 = api_client.post(URL, _payload(business, service, inicio_1))
    assert response_1.status_code == 201
    assert response_1.json()["is_first_booking_for_business"] is True

    inicio_2 = _aware_lima(fecha_abierta, time(11, 0))
    response_2 = api_client.post(URL, _payload(business, service, inicio_2))
    assert response_2.status_code == 201
    assert response_2.json()["is_first_booking_for_business"] is False


def test_race_condition_devuelve_409(
    api_client, cliente_user, business, service, fecha_abierta, monkeypatch
):
    inicio = _aware_lima(fecha_abierta, time(10, 0))
    fin = inicio + timedelta(minutes=service.duration_minutes)

    # Candado 2: alguien más ya tomó el slot en la BD.
    Booking.objects.create(
        customer=cliente_user,
        business=business,
        service=service,
        start_datetime=inicio,
        end_datetime=fin,
        price_at_booking=service.price,
        duration_at_booking=service.duration_minutes,
        status=Booking.Status.PENDING,
    )

    # Candado 1 "no se entera": simulamos que el motor de slots todavía
    # ve el horario como disponible (ventana de la race condition).
    import bookings.serializers as booking_serializers

    def _fake_calcular_slots(*args, **kwargs):
        return [Slot(inicio=inicio, fin=fin, disponible=True)]

    monkeypatch.setattr(booking_serializers, "calcular_slots", _fake_calcular_slots)

    api_client.force_authenticate(user=cliente_user)
    response = api_client.post(URL, _payload(business, service, inicio))

    assert response.status_code == 409
    assert response.json()["code"] == "slot_taken"
