from datetime import date, datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from bookings.models import Booking
from businesses.models import Business, Category, Service
from users.models import User

pytestmark = pytest.mark.django_db

LIMA_TZ = ZoneInfo("America/Lima")


def _aware(hora):
    fecha = date.today() + timedelta(days=1)
    return datetime.combine(fecha, hora, tzinfo=LIMA_TZ)


def _confirm_url(booking):
    return f"/api/bookings/{booking.id}/confirm/"


def _cancel_url(booking):
    return f"/api/bookings/{booking.id}/cancel/"


def _complete_url(booking):
    return f"/api/bookings/{booking.id}/complete/"


def _no_show_url(booking):
    return f"/api/bookings/{booking.id}/no-show/"


@pytest.fixture
def category(db):
    return Category.objects.create(name="Peluquería Test")


@pytest.fixture
def business(dueno_user, category):
    return Business.objects.create(
        owner=dueno_user,
        category=category,
        name="Salón Emails",
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
def customer(db):
    return User.objects.create_user(
        email="cliente-emails@test.pe",
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


def test_confirm_sobre_pending_manda_mail_de_confirmada(
    api_client,
    dueno_user,
    customer,
    _booking,
    mailoutbox,
    django_capture_on_commit_callbacks,
):
    booking = _booking(Booking.Status.PENDING)

    api_client.force_authenticate(user=dueno_user)
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(_confirm_url(booking))

    assert response.status_code == 200
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [customer.email]
    assert "confirmada" in mailoutbox[0].subject


def test_cancel_por_customer_sobre_confirmed_manda_mail_de_cancelada(
    api_client,
    customer,
    _booking,
    mailoutbox,
    django_capture_on_commit_callbacks,
):
    booking = _booking(Booking.Status.CONFIRMED)

    api_client.force_authenticate(user=customer)
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(_cancel_url(booking))

    assert response.status_code == 200
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [customer.email]
    assert "cancelada" in mailoutbox[0].subject


def test_complete_sobre_confirmed_manda_mail_de_completada(
    api_client,
    dueno_user,
    customer,
    _booking,
    mailoutbox,
    django_capture_on_commit_callbacks,
):
    booking = _booking(Booking.Status.CONFIRMED)

    api_client.force_authenticate(user=dueno_user)
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(_complete_url(booking))

    assert response.status_code == 200
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [customer.email]
    assert "Gracias por tu visita" in mailoutbox[0].subject


def test_no_show_sobre_confirmed_no_manda_mail(
    api_client,
    dueno_user,
    _booking,
    mailoutbox,
    django_capture_on_commit_callbacks,
):
    booking = _booking(Booking.Status.CONFIRMED)

    api_client.force_authenticate(user=dueno_user)
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(_no_show_url(booking))

    assert response.status_code == 200
    assert len(mailoutbox) == 0


def test_transicion_ilegal_no_registra_ni_manda_mail(
    api_client,
    dueno_user,
    _booking,
    mailoutbox,
    django_capture_on_commit_callbacks,
):
    booking = _booking(Booking.Status.COMPLETED)

    api_client.force_authenticate(user=dueno_user)
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(_confirm_url(booking))

    assert response.status_code == 409
    assert len(mailoutbox) == 0


def test_mail_caido_no_voltea_la_transicion_ya_commiteada(
    api_client,
    dueno_user,
    _booking,
    mailoutbox,
    django_capture_on_commit_callbacks,
):
    booking = _booking(Booking.Status.PENDING)

    api_client.force_authenticate(user=dueno_user)
    with patch("core.emails.send_mail", side_effect=Exception("SMTP caído")):
        with django_capture_on_commit_callbacks(execute=True):
            response = api_client.post(_confirm_url(booking))

    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED
    assert len(mailoutbox) == 0
