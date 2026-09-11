from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from bookings.emails import (
    email_reserva_cancelada,
    email_reserva_completada,
    email_reserva_confirmada,
)
from bookings.models import Booking
from businesses.models import Business, Category, Service
from users.models import User

pytestmark = pytest.mark.django_db

LIMA_TZ = ZoneInfo("America/Lima")


def _aware(hora):
    fecha = date.today() + timedelta(days=1)
    return datetime.combine(fecha, hora, tzinfo=LIMA_TZ)


@pytest.fixture
def category(db):
    return Category.objects.create(name="Peluquería Test")


@pytest.fixture
def dueno(db):
    return User.objects.create_user(
        email="dueno@test.pe", password="ClaveTest123", role=User.Role.DUENO
    )


@pytest.fixture
def business(dueno, category):
    return Business.objects.create(
        owner=dueno,
        category=category,
        name="Salón Bella Vista",
    )


@pytest.fixture
def service(business):
    return Service.objects.create(
        business=business,
        name="Corte de Cabello",
        duration_minutes=30,
        price="20.00",
    )


@pytest.fixture
def customer(db):
    return User.objects.create_user(
        email="cliente@test.pe",
        password="ClaveTest123",
        full_name="Juan Pérez",
    )


@pytest.fixture
def _booking(customer, business, service):
    def crear(status):
        inicio = _aware(time(11, 0))
        fin = _aware(time(11, 30))
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

    return crear


# --- email_reserva_confirmada ----------------------------------------------


def test_email_reserva_confirmada_envia_un_mail_correcto(
    mailoutbox, customer, business, service, _booking
):
    booking = _booking(Booking.Status.CONFIRMED)

    resultado = email_reserva_confirmada(booking)

    assert resultado is True
    assert len(mailoutbox) == 1
    mail = mailoutbox[0]
    assert mail.to == [customer.email]
    assert business.name in mail.subject
    assert "Juan Pérez" in mail.body
    assert service.name in mail.body


# --- email_reserva_cancelada -----------------------------------------------


def test_email_reserva_cancelada_envia_un_mail_correcto(
    mailoutbox, customer, business, service, _booking
):
    booking = _booking(Booking.Status.CANCELLED)

    resultado = email_reserva_cancelada(booking)

    assert resultado is True
    assert len(mailoutbox) == 1
    mail = mailoutbox[0]
    assert mail.to == [customer.email]
    assert business.name in mail.subject
    assert "Juan Pérez" in mail.body
    assert service.name in mail.body


# --- email_reserva_completada -----------------------------------------------


def test_email_reserva_completada_envia_un_mail_correcto(
    mailoutbox, customer, business, service, _booking
):
    booking = _booking(Booking.Status.COMPLETED)

    resultado = email_reserva_completada(booking)

    assert resultado is True
    assert len(mailoutbox) == 1
    mail = mailoutbox[0]
    assert mail.to == [customer.email]
    assert business.name in mail.subject
    assert "Juan Pérez" in mail.body
    assert service.name in mail.body


# --- saludo con fallback ----------------------------------------------


def test_saludo_sin_full_name_usa_fallback_cliente(mailoutbox, business, service):
    customer_sin_nombre = User.objects.create_user(
        email="sinnombre@test.pe", password="ClaveTest123"
    )
    inicio = _aware(time(11, 0))
    fin = _aware(time(11, 30))
    booking = Booking.objects.create(
        customer=customer_sin_nombre,
        business=business,
        service=service,
        start_datetime=inicio,
        end_datetime=fin,
        price_at_booking=service.price,
        duration_at_booking=service.duration_minutes,
        status=Booking.Status.CONFIRMED,
    )

    email_reserva_confirmada(booking)

    assert len(mailoutbox) == 1
    assert mailoutbox[0].body.startswith("Hola cliente")
