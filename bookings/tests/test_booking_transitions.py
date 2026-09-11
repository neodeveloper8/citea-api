from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from bookings.exceptions import TransicionInvalida
from bookings.models import Booking
from businesses.models import Business, Category, Service

pytestmark = pytest.mark.django_db

LIMA_TZ = ZoneInfo("America/Lima")


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
        name="Salón Transiciones",
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
def _booking(cliente_user, business, service):
    def crear(status):
        inicio = _aware(time(11, 0))
        fin = _aware(time(11, 30))
        return Booking.objects.create(
            customer=cliente_user,
            business=business,
            service=service,
            start_datetime=inicio,
            end_datetime=fin,
            price_at_booking=service.price,
            duration_at_booking=service.duration_minutes,
            status=status,
        )

    return crear


TODOS_LOS_ESTADOS = [
    Booking.Status.PENDING,
    Booking.Status.CONFIRMED,
    Booking.Status.CANCELLED,
    Booking.Status.COMPLETED,
    Booking.Status.NO_SHOW,
]


def _otros(*permitidos):
    return [s for s in TODOS_LOS_ESTADOS if s not in permitidos]


# --- confirmar() ---------------------------------------------------------


def test_confirmar_desde_pending_cambia_y_persiste(_booking):
    booking = _booking(Booking.Status.PENDING)

    booking.confirmar()

    assert booking.status == Booking.Status.CONFIRMED
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED


@pytest.mark.parametrize(
    "origen", _otros(Booking.Status.PENDING), ids=lambda s: s.value
)
def test_confirmar_desde_origen_ilegal_levanta_excepcion(_booking, origen):
    booking = _booking(origen)

    with pytest.raises(TransicionInvalida):
        booking.confirmar()


def test_confirmar_desde_origen_ilegal_no_persiste_cambio(_booking):
    booking = _booking(Booking.Status.CANCELLED)

    with pytest.raises(TransicionInvalida):
        booking.confirmar()

    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED


# --- cancelar() ------------------------------------------------------------


@pytest.mark.parametrize(
    "origen",
    [Booking.Status.PENDING, Booking.Status.CONFIRMED],
    ids=lambda s: s.value,
)
def test_cancelar_desde_origen_legal_cambia_y_persiste(_booking, origen):
    booking = _booking(origen)

    booking.cancelar()

    assert booking.status == Booking.Status.CANCELLED
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED


@pytest.mark.parametrize(
    "origen",
    _otros(Booking.Status.PENDING, Booking.Status.CONFIRMED),
    ids=lambda s: s.value,
)
def test_cancelar_desde_estado_terminal_levanta_excepcion(_booking, origen):
    booking = _booking(origen)

    with pytest.raises(TransicionInvalida):
        booking.cancelar()


def test_cancelar_desde_origen_ilegal_no_persiste_cambio(_booking):
    booking = _booking(Booking.Status.COMPLETED)

    with pytest.raises(TransicionInvalida):
        booking.cancelar()

    booking.refresh_from_db()
    assert booking.status == Booking.Status.COMPLETED


# --- completar() -----------------------------------------------------------


def test_completar_desde_confirmed_cambia_y_persiste(_booking):
    booking = _booking(Booking.Status.CONFIRMED)

    booking.completar()

    assert booking.status == Booking.Status.COMPLETED
    booking.refresh_from_db()
    assert booking.status == Booking.Status.COMPLETED


@pytest.mark.parametrize(
    "origen", _otros(Booking.Status.CONFIRMED), ids=lambda s: s.value
)
def test_completar_desde_origen_ilegal_levanta_excepcion(_booking, origen):
    booking = _booking(origen)

    with pytest.raises(TransicionInvalida):
        booking.completar()


def test_completar_desde_origen_ilegal_no_persiste_cambio(_booking):
    booking = _booking(Booking.Status.PENDING)

    with pytest.raises(TransicionInvalida):
        booking.completar()

    booking.refresh_from_db()
    assert booking.status == Booking.Status.PENDING


# --- marcar_no_show() --------------------------------------------------


def test_marcar_no_show_desde_confirmed_cambia_y_persiste(_booking):
    booking = _booking(Booking.Status.CONFIRMED)

    booking.marcar_no_show()

    assert booking.status == Booking.Status.NO_SHOW
    booking.refresh_from_db()
    assert booking.status == Booking.Status.NO_SHOW


@pytest.mark.parametrize(
    "origen", _otros(Booking.Status.CONFIRMED), ids=lambda s: s.value
)
def test_marcar_no_show_desde_origen_ilegal_levanta_excepcion(_booking, origen):
    booking = _booking(origen)

    with pytest.raises(TransicionInvalida):
        booking.marcar_no_show()


def test_marcar_no_show_desde_origen_ilegal_no_persiste_cambio(_booking):
    booking = _booking(Booking.Status.NO_SHOW)

    with pytest.raises(TransicionInvalida):
        booking.marcar_no_show()

    booking.refresh_from_db()
    assert booking.status == Booking.Status.NO_SHOW


# --- Detalle de la excepción -------------------------------------------


def test_excepcion_trae_estado_accion_y_permitidos(_booking):
    booking = _booking(Booking.Status.COMPLETED)

    with pytest.raises(TransicionInvalida) as exc_info:
        booking.confirmar()

    exc = exc_info.value
    assert exc.estado_actual == Booking.Status.COMPLETED
    assert exc.accion == "confirmar"
    assert exc.permitidos == {Booking.Status.PENDING}
