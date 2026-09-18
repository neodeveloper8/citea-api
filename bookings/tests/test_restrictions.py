from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from bookings.models import Booking
from bookings.restrictions import contar_noshows_recientes, esta_restringido
from businesses.models import Business, BusinessHours, Category, Service
from users.models import User

pytestmark = pytest.mark.django_db

LIMA_TZ = ZoneInfo("America/Lima")
WEEKDAY_ABIERTO = 0  # lunes

AHORA = datetime(2026, 6, 15, 12, 0, tzinfo=LIMA_TZ)


def _aware(dias_atras, hora=time(11, 0)):
    """Fecha relativa a AHORA (no a date.today()), como pide la tarea."""
    fecha = (AHORA - timedelta(days=dias_atras)).date()
    return datetime.combine(fecha, hora, tzinfo=LIMA_TZ)


@pytest.fixture
def category(db):
    return Category.objects.create(name="Peluquería Test")


@pytest.fixture
def dueno(db):
    return User.objects.create_user(
        email="dueno-restrict@test.pe", password="ClaveTest123", role=User.Role.DUENO
    )


@pytest.fixture
def business(dueno, category):
    return Business.objects.create(
        owner=dueno,
        category=category,
        name="Salón Restricciones",
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
def cliente(db):
    return User.objects.create_user(
        email="cliente-restrict@test.pe", password="ClaveTest123"
    )


def _no_show(customer, business, service, dias_atras):
    inicio = _aware(dias_atras, time(11, 0))
    fin = inicio + timedelta(minutes=service.duration_minutes)
    return Booking.objects.create(
        customer=customer,
        business=business,
        service=service,
        start_datetime=inicio,
        end_datetime=fin,
        price_at_booking=service.price,
        duration_at_booking=service.duration_minutes,
        status=Booking.Status.NO_SHOW,
    )


# =========================================================================
# A NIVEL FUNCIÓN (pura, reloj fijo)
# =========================================================================


def test_sin_noshows_count_cero_no_restringido(cliente, business):
    count = contar_noshows_recientes(customer=cliente, business=business, ahora=AHORA)
    assert count == 0
    assert esta_restringido(customer=cliente, business=business, ahora=AHORA) is False


def test_un_noshow_reciente_no_restringido(cliente, business, service):
    _no_show(cliente, business, service, dias_atras=10)

    count = contar_noshows_recientes(customer=cliente, business=business, ahora=AHORA)
    assert count == 1
    assert esta_restringido(customer=cliente, business=business, ahora=AHORA) is False


def test_dos_noshows_recientes_restringido(cliente, business, service):
    _no_show(cliente, business, service, dias_atras=10)
    _no_show(cliente, business, service, dias_atras=20)

    assert esta_restringido(customer=cliente, business=business, ahora=AHORA) is True


def test_ventana_movil_descarta_noshow_viejo(cliente, business, service):
    _no_show(cliente, business, service, dias_atras=10)  # dentro de ventana
    _no_show(cliente, business, service, dias_atras=100)  # fuera (>90 días)

    count = contar_noshows_recientes(customer=cliente, business=business, ahora=AHORA)
    assert count == 1
    assert esta_restringido(customer=cliente, business=business, ahora=AHORA) is False


def test_noshows_en_otro_negocio_no_cuentan(
    cliente, service, business, category, dueno
):
    otro_business = Business.objects.create(
        owner=dueno,
        category=category,
        name="Otro Salón",
        status=Business.Status.APPROVED,
    )
    otro_service = Service.objects.create(
        business=otro_business,
        name="Corte",
        duration_minutes=30,
        price="20.00",
    )
    _no_show(cliente, otro_business, otro_service, dias_atras=10)
    _no_show(cliente, otro_business, otro_service, dias_atras=20)

    # Restringido en otro_business, pero NO en business (el consultado).
    assert (
        esta_restringido(customer=cliente, business=otro_business, ahora=AHORA) is True
    )
    assert esta_restringido(customer=cliente, business=business, ahora=AHORA) is False


# =========================================================================
# A NIVEL ENDPOINT (POST /api/bookings/)
# =========================================================================

URL = "/api/bookings/"


def _proxima_fecha_con_weekday(weekday, desde=None):
    base = desde or date.today()
    for delta in range(1, 8):
        candidata = base + timedelta(days=delta)
        if candidata.weekday() == weekday:
            return candidata
    raise AssertionError("No se encontró fecha con ese weekday.")


@pytest.fixture
def business_hours(business):
    return BusinessHours.objects.create(
        business=business,
        weekday=WEEKDAY_ABIERTO,
        open_time=time(10, 0),
        close_time=time(18, 0),
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


def _no_show_reciente(customer, business, service):
    """no-show dentro de la ventana móvil, relativo a hoy (para el endpoint,
    que usa timezone.now() real, no el reloj fijo de los tests de función)."""
    inicio_lima = datetime.combine(
        date.today() - timedelta(days=10), time(11, 0), tzinfo=LIMA_TZ
    )
    fin = inicio_lima + timedelta(minutes=service.duration_minutes)
    return Booking.objects.create(
        customer=customer,
        business=business,
        service=service,
        start_datetime=inicio_lima,
        end_datetime=fin,
        price_at_booking=service.price,
        duration_at_booking=service.duration_minutes,
        status=Booking.Status.NO_SHOW,
    )


def test_endpoint_dos_noshows_recientes_da_403(
    api_client, cliente, business, service, fecha_abierta
):
    _no_show_reciente(cliente, business, service)
    _no_show_reciente(cliente, business, service)

    inicio = datetime.combine(fecha_abierta, time(10, 0), tzinfo=LIMA_TZ)

    api_client.force_authenticate(user=cliente)
    response = api_client.post(URL, _payload(business, service, inicio))

    assert response.status_code == 403
    assert response.json()["code"] == "cliente_restringido"
    assert not Booking.objects.filter(
        customer=cliente, business=business, status=Booking.Status.PENDING
    ).exists()


def test_endpoint_un_noshow_no_frena_la_reserva(
    api_client, cliente, business, service, fecha_abierta
):
    _no_show_reciente(cliente, business, service)

    inicio = datetime.combine(fecha_abierta, time(10, 0), tzinfo=LIMA_TZ)

    api_client.force_authenticate(user=cliente)
    response = api_client.post(URL, _payload(business, service, inicio))

    assert response.status_code == 201


def test_endpoint_noshows_en_otro_negocio_no_frenan_esta_reserva(
    api_client, cliente, business, service, fecha_abierta, category, dueno
):
    otro_business = Business.objects.create(
        owner=dueno,
        category=category,
        name="Otro Salón Endpoint",
        status=Business.Status.APPROVED,
    )
    otro_service = Service.objects.create(
        business=otro_business,
        name="Corte",
        duration_minutes=30,
        price="20.00",
    )
    _no_show_reciente(cliente, otro_business, otro_service)
    _no_show_reciente(cliente, otro_business, otro_service)

    inicio = datetime.combine(fecha_abierta, time(10, 0), tzinfo=LIMA_TZ)

    api_client.force_authenticate(user=cliente)
    response = api_client.post(URL, _payload(business, service, inicio))

    assert response.status_code == 201
