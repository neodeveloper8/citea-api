import csv
import io
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from bookings.exports import COLUMNAS, generar_csv, recolectar_clientes
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
        name="Salón Export",
        status=Business.Status.APPROVED,
    )


@pytest.fixture
def otro_dueno(db):
    return User.objects.create_user(
        email="otro-dueno@test.pe", password="ClaveTest123", role=User.Role.DUENO
    )


@pytest.fixture
def service(business):
    return Service.objects.create(
        business=business, name="Corte", duration_minutes=30, price="20.00"
    )


@pytest.fixture
def service_barba(business):
    return Service.objects.create(
        business=business, name="Barba", duration_minutes=15, price="10.00"
    )


def _cliente(email, full_name=""):
    return User.objects.create_user(
        email=email, password="ClaveTest123", full_name=full_name
    )


def _booking(customer, business, service, status, dias_atras):
    inicio = _aware(dias_atras)
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
    )


# =========================================================================
# A NIVEL FUNCIÓN: recolectar_clientes
# =========================================================================


def test_dos_clientes_con_completed_visitas_correctas_y_orden(business, service):
    cliente_a = _cliente("a@test.pe", "Cliente A")
    cliente_b = _cliente("b@test.pe", "Cliente B")

    _booking(cliente_a, business, service, Booking.Status.COMPLETED, dias_atras=10)
    _booking(cliente_a, business, service, Booking.Status.COMPLETED, dias_atras=20)
    _booking(cliente_a, business, service, Booking.Status.COMPLETED, dias_atras=30)
    _booking(cliente_b, business, service, Booking.Status.COMPLETED, dias_atras=5)

    filas = recolectar_clientes(business)

    assert len(filas) == 2
    assert filas[0]["email"] == cliente_a.email
    assert filas[0]["visitas"] == 3
    assert filas[1]["email"] == cliente_b.email
    assert filas[1]["visitas"] == 1


def test_cliente_sin_ningun_completed_no_aparece(business, service):
    cliente = _cliente("sincompleted@test.pe", "Sin Completed")
    _booking(cliente, business, service, Booking.Status.PENDING, dias_atras=1)
    _booking(cliente, business, service, Booking.Status.CANCELLED, dias_atras=2)
    _booking(cliente, business, service, Booking.Status.NO_SHOW, dias_atras=3)

    filas = recolectar_clientes(business)

    assert filas == []


def test_cliente_de_otro_negocio_no_aparece(business, service, category, dueno_user):
    otro_business = Business.objects.create(
        owner=dueno_user,
        category=category,
        name="Otro Salón",
        status=Business.Status.APPROVED,
    )
    otro_service = Service.objects.create(
        business=otro_business, name="Corte", duration_minutes=30, price="20.00"
    )
    cliente_ajeno = _cliente("ajeno@test.pe", "Cliente Ajeno")
    _booking(
        cliente_ajeno,
        otro_business,
        otro_service,
        Booking.Status.COMPLETED,
        dias_atras=1,
    )

    filas = recolectar_clientes(business)

    assert filas == []


def test_servicio_mas_frecuente_es_el_de_mayor_conteo(business, service, service_barba):
    cliente = _cliente("servicios@test.pe", "Cliente Servicios")
    _booking(cliente, business, service, Booking.Status.COMPLETED, dias_atras=10)
    _booking(cliente, business, service, Booking.Status.COMPLETED, dias_atras=20)
    _booking(cliente, business, service_barba, Booking.Status.COMPLETED, dias_atras=30)

    filas = recolectar_clientes(business)

    assert len(filas) == 1
    assert filas[0]["servicio_mas_frecuente"] == "Corte"


def test_ultima_visita_es_la_fecha_del_completed_mas_reciente(business, service):
    cliente = _cliente("ultima@test.pe", "Cliente Ultima")
    _booking(cliente, business, service, Booking.Status.COMPLETED, dias_atras=30)
    reciente = _booking(
        cliente, business, service, Booking.Status.COMPLETED, dias_atras=5
    )

    filas = recolectar_clientes(business)

    assert len(filas) == 1
    assert filas[0]["ultima_visita"] == reciente.start_datetime.date().isoformat()


# =========================================================================
# A NIVEL FUNCIÓN: generar_csv
# =========================================================================


def test_generar_csv_produce_header_y_filas_parseables():
    filas = [
        {
            "nombre": "Juan Pérez",
            "email": "juan@test.pe",
            "telefono": "999888777",
            "visitas": 3,
            "ultima_visita": "2026-06-01",
            "servicio_mas_frecuente": "Corte",
        },
        {
            "nombre": "Ana Torres",
            "email": "ana@test.pe",
            "telefono": "999888666",
            "visitas": 1,
            "ultima_visita": "2026-05-15",
            "servicio_mas_frecuente": "Barba",
        },
    ]

    csv_str = generar_csv(filas)
    reader = csv.DictReader(io.StringIO(csv_str))

    assert reader.fieldnames == COLUMNAS
    leidas = list(reader)
    assert len(leidas) == 2
    assert leidas[0]["nombre"] == "Juan Pérez"
    assert leidas[0]["email"] == "juan@test.pe"
    assert leidas[1]["nombre"] == "Ana Torres"


# =========================================================================
# A NIVEL ENDPOINT
# =========================================================================


def _export_url(business):
    return f"/api/bookings/business/{business.slug}/export/"


def test_dueno_exporta_su_negocio_devuelve_csv_valido(
    api_client, dueno_user, business, service
):
    cliente = _cliente("export-feliz@test.pe", "Cliente Feliz")
    _booking(cliente, business, service, Booking.Status.COMPLETED, dias_atras=10)

    api_client.force_authenticate(user=dueno_user)
    response = api_client.get(_export_url(business))

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert (
        response["Content-Disposition"]
        == f'attachment; filename="clientes_{business.slug}.csv"'
    )

    reader = csv.DictReader(io.StringIO(response.content.decode("utf-8")))
    filas = list(reader)
    assert len(filas) == 1
    assert filas[0]["email"] == cliente.email
    assert filas[0]["visitas"] == "1"


def test_dueno_ajeno_da_404(api_client, otro_dueno, business):
    api_client.force_authenticate(user=otro_dueno)
    response = api_client.get(_export_url(business))

    assert response.status_code == 404


def test_cliente_autenticado_da_403(api_client, cliente_user, business):
    api_client.force_authenticate(user=cliente_user)
    response = api_client.get(_export_url(business))

    assert response.status_code == 403


def test_sin_autenticacion_da_401(api_client, business):
    response = api_client.get(_export_url(business))

    assert response.status_code == 401


def test_negocio_sin_clientes_completed_da_csv_solo_header(
    api_client, dueno_user, business
):
    api_client.force_authenticate(user=dueno_user)
    response = api_client.get(_export_url(business))

    assert response.status_code == 200
    reader = csv.DictReader(io.StringIO(response.content.decode("utf-8")))
    assert reader.fieldnames == COLUMNAS
    assert list(reader) == []
