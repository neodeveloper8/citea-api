from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.db import IntegrityError, transaction

from bookings.models import Booking
from businesses.models import Business, Category, Service
from users.models import User

LIMA_TZ = ZoneInfo("America/Lima")


def _aware(hora):
    fecha = date.today() + timedelta(days=1)
    return datetime.combine(fecha, hora, tzinfo=LIMA_TZ)


@pytest.fixture
def customer():
    return User.objects.create_user(email="cliente@test.com", password="clave123")


@pytest.fixture
def category():
    return Category.objects.create(name="Peluquería")


@pytest.fixture
def business(category):
    owner = User.objects.create_user(email="dueno@test.com", password="clave123")
    return Business.objects.create(owner=owner, category=category, name="Salón Uno")


@pytest.fixture
def service(business):
    return Service.objects.create(
        business=business,
        name="Corte",
        duration_minutes=45,
        price=50,
    )


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


@pytest.mark.django_db
def test_dos_reservas_solapadas_mismo_negocio_falla(customer, business, service):
    _crear_booking(
        customer,
        business,
        service,
        _aware(time(11, 0)),
        _aware(time(11, 45)),
        Booking.Status.PENDING,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _crear_booking(
                customer,
                business,
                service,
                _aware(time(11, 30)),
                _aware(time(12, 0)),
                Booking.Status.CONFIRMED,
            )


@pytest.mark.django_db
def test_reservas_adyacentes_no_solapan(customer, business, service):
    _crear_booking(
        customer,
        business,
        service,
        _aware(time(11, 0)),
        _aware(time(11, 45)),
        Booking.Status.PENDING,
    )

    _crear_booking(
        customer,
        business,
        service,
        _aware(time(11, 45)),
        _aware(time(12, 15)),
        Booking.Status.CONFIRMED,
    )


@pytest.mark.django_db
def test_solape_en_negocios_distintos_esta_permitido(
    customer, business, service, category
):
    otro_owner = User.objects.create_user(
        email="otro-dueno@test.com", password="clave123"
    )
    otro_business = Business.objects.create(
        owner=otro_owner,
        category=category,
        name="Salón Dos",
    )
    otro_service = Service.objects.create(
        business=otro_business,
        name="Corte",
        duration_minutes=45,
        price=50,
    )

    _crear_booking(
        customer,
        business,
        service,
        _aware(time(11, 0)),
        _aware(time(11, 45)),
        Booking.Status.PENDING,
    )

    _crear_booking(
        customer,
        otro_business,
        otro_service,
        _aware(time(11, 0)),
        _aware(time(11, 45)),
        Booking.Status.PENDING,
    )


@pytest.mark.django_db
def test_reserva_cancelada_no_bloquea_el_slot(customer, business, service):
    _crear_booking(
        customer,
        business,
        service,
        _aware(time(11, 0)),
        _aware(time(11, 45)),
        Booking.Status.CANCELLED,
    )

    _crear_booking(
        customer,
        business,
        service,
        _aware(time(11, 0)),
        _aware(time(11, 45)),
        Booking.Status.PENDING,
    )


@pytest.mark.django_db
def test_dos_pending_identicos_mismo_negocio_falla(customer, business, service):
    _crear_booking(
        customer,
        business,
        service,
        _aware(time(11, 0)),
        _aware(time(11, 45)),
        Booking.Status.PENDING,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _crear_booking(
                customer,
                business,
                service,
                _aware(time(11, 0)),
                _aware(time(11, 45)),
                Booking.Status.PENDING,
            )
