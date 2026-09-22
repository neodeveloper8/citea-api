from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.db import IntegrityError, transaction

from bookings.emails import email_reserva_confirmada
from bookings.exports import recolectar_clientes
from bookings.models import Booking
from businesses.models import Business, Category, Service
from users.models import User

pytestmark = pytest.mark.django_db

LIMA_TZ = ZoneInfo("America/Lima")


def _aware(dias_atras, hora=time(11, 0)):
    fecha = date.today() - timedelta(days=dias_atras)
    return datetime.combine(fecha, hora, tzinfo=LIMA_TZ)


@pytest.fixture
def category(db):
    return Category.objects.create(name="Peluquería Test")


@pytest.fixture
def business(dueno_user, category):
    return Business.objects.create(
        owner=dueno_user,
        category=category,
        name="Salón Guests",
        status=Business.Status.APPROVED,
    )


@pytest.fixture
def service(business):
    return Service.objects.create(
        business=business, name="Corte", duration_minutes=30, price="20.00"
    )


def _booking_kwargs(business, service, dias_atras, **overrides):
    inicio = _aware(dias_atras)
    fin = inicio + timedelta(minutes=service.duration_minutes)
    kwargs = dict(
        business=business,
        service=service,
        start_datetime=inicio,
        end_datetime=fin,
        price_at_booking=service.price,
        duration_at_booking=service.duration_minutes,
        status=Booking.Status.COMPLETED,
    )
    kwargs.update(overrides)
    return kwargs


# =========================================================================
# A NIVEL MODELO: constraint XOR customer/guest_name
# =========================================================================


def test_customer_none_con_guest_name_se_persiste_ok(business, service):
    booking = Booking.objects.create(
        **_booking_kwargs(
            business, service, dias_atras=1, customer=None, guest_name="María"
        )
    )
    booking.refresh_from_db()
    assert booking.customer is None
    assert booking.guest_name == "María"


def test_customer_none_y_guest_name_vacio_viola_constraint(business, service):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Booking.objects.create(
                **_booking_kwargs(
                    business, service, dias_atras=1, customer=None, guest_name=""
                )
            )


def test_customer_y_guest_name_juntos_viola_constraint(business, service, cliente_user):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Booking.objects.create(
                **_booking_kwargs(
                    business,
                    service,
                    dias_atras=1,
                    customer=cliente_user,
                    guest_name="X",
                )
            )


# =========================================================================
# emails: guard customer=None
# =========================================================================


def test_email_reserva_confirmada_con_guest_no_manda_y_devuelve_false(
    mailoutbox, business, service
):
    booking = Booking.objects.create(
        **_booking_kwargs(
            business,
            service,
            dias_atras=1,
            status=Booking.Status.CONFIRMED,
            customer=None,
            guest_name="Pedro Tel",
        )
    )

    resultado = email_reserva_confirmada(booking)

    assert resultado is False
    assert len(mailoutbox) == 0


# =========================================================================
# exports: guests aparecen sin deduplicar
# =========================================================================


def test_recolectar_clientes_incluye_cliente_con_cuenta_y_guest(business, service):
    cliente = User.objects.create_user(
        email="cliente-cuenta@test.pe",
        password="ClaveTest123",
        full_name="Cliente Cuenta",
    )
    Booking.objects.create(
        **_booking_kwargs(business, service, dias_atras=10, customer=cliente)
    )
    Booking.objects.create(
        **_booking_kwargs(business, service, dias_atras=20, customer=cliente)
    )
    Booking.objects.create(
        **_booking_kwargs(
            business,
            service,
            dias_atras=5,
            customer=None,
            guest_name="Pedro Tel",
            guest_phone="987654321",
        )
    )

    filas = recolectar_clientes(business)

    assert len(filas) == 2
    por_nombre = {f["nombre"]: f for f in filas}

    fila_cliente = por_nombre["Cliente Cuenta"]
    assert fila_cliente["visitas"] == 2
    assert fila_cliente["email"] == cliente.email

    fila_guest = por_nombre["Pedro Tel"]
    assert fila_guest["email"] == ""
    assert fila_guest["telefono"] == "987654321"
    assert fila_guest["visitas"] == 1
