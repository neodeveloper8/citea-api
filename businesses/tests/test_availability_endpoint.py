from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from bookings.models import Booking
from businesses.models import Business, BusinessHours, Category, Service

pytestmark = pytest.mark.django_db

WEEKDAY_ABIERTO = 0  # lunes
LIMA_TZ = ZoneInfo("America/Lima")


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


def _url(business):
    return f"/api/businesses/{business.slug}/availability/"


@pytest.fixture
def category(db):
    return Category.objects.create(name="Peluquería Test")


@pytest.fixture
def business(dueno_user, category):
    return Business.objects.create(
        owner=dueno_user,
        category=category,
        name="Salón Disponibilidad",
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


def test_happy_path_devuelve_slots(api_client, business, service, fecha_abierta):
    response = api_client.get(
        _url(business), {"date": fecha_abierta.isoformat(), "service": service.id}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["slots"], "se esperaban slots para un día abierto sin reservas"
    primero = data["slots"][0]
    assert set(primero.keys()) == {"inicio", "fin", "disponible"}


def test_date_faltante_da_400(api_client, business, service):
    response = api_client.get(_url(business), {"service": service.id})
    assert response.status_code == 400


def test_date_mal_formada_da_400(api_client, business, service, fecha_abierta):
    response = api_client.get(_url(business), {"date": "manana", "service": service.id})
    assert response.status_code == 400


def test_service_faltante_da_400(api_client, business, fecha_abierta):
    response = api_client.get(_url(business), {"date": fecha_abierta.isoformat()})
    assert response.status_code == 400


def test_service_no_numerico_da_400(api_client, business, fecha_abierta):
    response = api_client.get(
        _url(business), {"date": fecha_abierta.isoformat(), "service": "abc"}
    )
    assert response.status_code == 400


def test_service_inexistente_da_404(api_client, business, fecha_abierta):
    response = api_client.get(
        _url(business), {"date": fecha_abierta.isoformat(), "service": 999999}
    )
    assert response.status_code == 404


def test_service_de_otro_negocio_da_404(
    api_client, business, fecha_abierta, dueno_user, category
):
    otro_negocio = Business.objects.create(
        owner=dueno_user,
        category=category,
        name="Otro Salón",
        status=Business.Status.APPROVED,
    )
    service_ajeno = Service.objects.create(
        business=otro_negocio,
        name="Servicio ajeno",
        duration_minutes=30,
        price="15.00",
    )

    response = api_client.get(
        _url(business), {"date": fecha_abierta.isoformat(), "service": service_ajeno.id}
    )
    assert response.status_code == 404


def test_slug_inexistente_da_404(api_client, service, fecha_abierta):
    response = api_client.get(
        "/api/businesses/no-existe-este-slug/availability/",
        {"date": fecha_abierta.isoformat(), "service": service.id},
    )
    assert response.status_code == 404


def test_negocio_draft_anonimo_da_404(api_client, dueno_user, category, fecha_abierta):
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

    response = api_client.get(
        _url(negocio_draft),
        {"date": fecha_abierta.isoformat(), "service": service_draft.id},
    )
    assert response.status_code == 404


def test_negocio_draft_dueno_autenticado_da_200(
    api_client, dueno_user, category, fecha_abierta
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

    api_client.force_authenticate(user=dueno_user)
    response = api_client.get(
        _url(negocio_draft),
        {"date": fecha_abierta.isoformat(), "service": service_draft.id},
    )
    assert response.status_code == 200


def test_booking_pending_ocupa_el_slot(
    api_client, cliente_user, business, service, fecha_abierta
):
    inicio = _aware_lima(fecha_abierta, time(11, 0))
    fin = _aware_lima(fecha_abierta, time(11, 30))
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

    response = api_client.get(
        _url(business), {"date": fecha_abierta.isoformat(), "service": service.id}
    )

    assert response.status_code == 200
    por_hora = {
        slot["inicio"][11:16]: slot["disponible"] for slot in response.json()["slots"]
    }
    assert por_hora["11:00"] is False


def test_booking_cancelled_no_ocupa_el_slot(
    api_client, cliente_user, business, service, fecha_abierta
):
    inicio = _aware_lima(fecha_abierta, time(11, 0))
    fin = _aware_lima(fecha_abierta, time(11, 30))
    Booking.objects.create(
        customer=cliente_user,
        business=business,
        service=service,
        start_datetime=inicio,
        end_datetime=fin,
        price_at_booking=service.price,
        duration_at_booking=service.duration_minutes,
        status=Booking.Status.CANCELLED,
    )

    response = api_client.get(
        _url(business), {"date": fecha_abierta.isoformat(), "service": service.id}
    )

    assert response.status_code == 200
    por_hora = {
        slot["inicio"][11:16]: slot["disponible"] for slot in response.json()["slots"]
    }
    assert por_hora["11:00"] is True


def test_date_en_el_pasado_devuelve_slots_vacio(api_client, business, service):
    ayer = date.today() - timedelta(days=1)
    BusinessHours.objects.create(
        business=business,
        weekday=ayer.weekday(),
        open_time=time(10, 0),
        close_time=time(18, 0),
    )

    response = api_client.get(
        _url(business), {"date": ayer.isoformat(), "service": service.id}
    )

    assert response.status_code == 200
    assert response.json()["slots"] == []


def test_weekday_sin_hours_devuelve_slots_vacio(api_client, business, service):
    # business tiene hours solo para WEEKDAY_ABIERTO (lunes); elegimos otro día.
    BusinessHours.objects.create(
        business=business,
        weekday=WEEKDAY_ABIERTO,
        open_time=time(10, 0),
        close_time=time(18, 0),
    )
    fecha_cerrada = _proxima_fecha_con_weekday((WEEKDAY_ABIERTO + 1) % 7)

    response = api_client.get(
        _url(business), {"date": fecha_cerrada.isoformat(), "service": service.id}
    )

    assert response.status_code == 200
    assert response.json()["slots"] == []
