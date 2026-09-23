from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from bookings.models import Booking
from bookings.tasks import enviar_recordatorios
from businesses.models import Business, Category, Service
from users.models import User

pytestmark = pytest.mark.django_db

LIMA_TZ = ZoneInfo("America/Lima")

# Reloj fijo inyectado: los start_datetime se construyen relativos a AHORA,
# no a timezone.now(), para no depender de cuándo corren los tests.
AHORA = datetime(2026, 6, 15, 12, 0, tzinfo=LIMA_TZ)


@pytest.fixture
def category(db):
    return Category.objects.create(name="Peluquería Test")


@pytest.fixture
def dueno(db):
    return User.objects.create_user(
        email="dueno-recordatorio@test.pe",
        password="ClaveTest123",
        role=User.Role.DUENO,
    )


@pytest.fixture
def business(dueno, category):
    return Business.objects.create(
        owner=dueno,
        category=category,
        name="Salón Recordatorios",
        status=Business.Status.APPROVED,
    )


@pytest.fixture
def service(business):
    return Service.objects.create(
        business=business, name="Corte", duration_minutes=30, price="20.00"
    )


@pytest.fixture
def cliente(db):
    return User.objects.create_user(
        email="cliente-recordatorio@test.pe",
        password="ClaveTest123",
        full_name="Juan Pérez",
    )


@pytest.fixture
def _booking(business, service, cliente):
    def crear(
        horas_desde_ahora,
        status=Booking.Status.CONFIRMED,
        customer="__default__",
        reminder_sent_at=None,
        guest_name="",
        guest_phone="",
    ):
        if customer == "__default__":
            customer = cliente
        inicio = AHORA + timedelta(hours=horas_desde_ahora)
        fin = inicio + timedelta(minutes=service.duration_minutes)
        return Booking.objects.create(
            customer=customer,
            business=business,
            service=service,
            start_datetime=inicio,
            end_datetime=fin,
            price_at_booking=service.price,
            duration_at_booking=service.duration_minutes,
            status=status,
            reminder_sent_at=reminder_sent_at,
            guest_name=guest_name,
            guest_phone=guest_phone,
        )

    return crear


# --- Camino feliz: dentro de la franja ---------------------------------


def test_confirmed_en_franja_recibe_recordatorio(mailoutbox, cliente, _booking):
    booking = _booking(23.5)

    procesados = enviar_recordatorios(AHORA)

    assert procesados == 1
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [cliente.email]

    booking.refresh_from_db()
    assert booking.reminder_sent_at is not None


# --- Fuera de la franja --------------------------------------------------


def test_confirmed_muy_pronto_no_recibe(mailoutbox, _booking):
    booking = _booking(10)

    procesados = enviar_recordatorios(AHORA)

    assert procesados == 0
    assert len(mailoutbox) == 0
    booking.refresh_from_db()
    assert booking.reminder_sent_at is None


def test_confirmed_muy_lejos_no_recibe(mailoutbox, _booking):
    booking = _booking(30)

    procesados = enviar_recordatorios(AHORA)

    assert procesados == 0
    assert len(mailoutbox) == 0
    booking.refresh_from_db()
    assert booking.reminder_sent_at is None


# --- Filtros de estado / marca / guest -----------------------------------


def test_pending_en_franja_no_recibe(mailoutbox, _booking):
    booking = _booking(23.5, status=Booking.Status.PENDING)

    procesados = enviar_recordatorios(AHORA)

    assert procesados == 0
    assert len(mailoutbox) == 0
    booking.refresh_from_db()
    assert booking.reminder_sent_at is None


def test_ya_recordado_no_vuelve_a_recibir(mailoutbox, _booking):
    ya = AHORA - timedelta(hours=1)
    _booking(23.5, reminder_sent_at=ya)

    procesados = enviar_recordatorios(AHORA)

    assert procesados == 0
    assert len(mailoutbox) == 0


def test_booking_direct_guest_no_recibe_ni_crashea(mailoutbox, _booking):
    booking = _booking(23.5, customer=None, guest_name="Pedro Tel", guest_phone="999")

    procesados = enviar_recordatorios(AHORA)

    assert procesados == 0
    assert len(mailoutbox) == 0
    booking.refresh_from_db()
    assert booking.reminder_sent_at is None


# --- Idempotencia ---------------------------------------------------------


def test_dos_corridas_seguidas_mandan_un_solo_mail(mailoutbox, _booking):
    _booking(23.5)

    primera = enviar_recordatorios(AHORA)
    segunda = enviar_recordatorios(AHORA)

    assert primera == 1
    assert segunda == 0
    assert len(mailoutbox) == 1


# --- Mail caído: best-effort ---------------------------------------------


def test_mail_caido_igual_marca_reminder_sent_at(mailoutbox, _booking):
    booking = _booking(23.5)

    with patch("core.emails.send_mail", side_effect=Exception("SMTP caído")):
        procesados = enviar_recordatorios(AHORA)

    assert procesados == 1
    assert len(mailoutbox) == 0

    booking.refresh_from_db()
    assert booking.reminder_sent_at is not None


# --- Contador devuelto ----------------------------------------------------


def test_devuelve_la_cantidad_procesada(mailoutbox, _booking):
    # Dos en franja, sin solaparse entre sí (el servicio dura 30 min).
    _booking(23.1)
    _booking(23.7)
    _booking(10)  # fuera de franja, no cuenta

    procesados = enviar_recordatorios(AHORA)

    assert procesados == 2
    assert len(mailoutbox) == 2
