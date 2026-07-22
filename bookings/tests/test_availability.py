from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from bookings.availability import calcular_slots

LIMA_TZ = ZoneInfo("America/Lima")


def _aware(fecha, hora):
    return datetime.combine(fecha, hora, tzinfo=LIMA_TZ)


def test_dia_normal_un_tramo_sin_reservas():
    fecha = date.today() + timedelta(days=1)
    ahora = _aware(date.today(), time(9, 0))

    slots = calcular_slots(
        tramos_del_dia=[(time(10, 0), time(18, 0))],
        reservas_del_dia=[],
        duracion_servicio=30,
        fecha=fecha,
        ahora=ahora,
        paso=15,
    )

    assert slots[0].inicio == _aware(fecha, time(10, 0))
    assert slots[-1].inicio == _aware(fecha, time(17, 30))
    assert all(s.disponible for s in slots)

    inicios = [s.inicio for s in slots]
    for anterior, siguiente in zip(inicios, inicios[1:]):
        assert siguiente - anterior == timedelta(minutes=15)


def test_ultimo_slot_entra_justo_antes_del_cierre():
    fecha = date.today() + timedelta(days=1)
    ahora = _aware(date.today(), time(9, 0))

    slots = calcular_slots(
        tramos_del_dia=[(time(10, 0), time(18, 0))],
        reservas_del_dia=[],
        duracion_servicio=45,
        fecha=fecha,
        ahora=ahora,
        paso=15,
    )

    inicios = [s.inicio for s in slots]
    assert _aware(fecha, time(17, 15)) in inicios
    assert _aware(fecha, time(17, 30)) not in inicios


def test_horario_partido_no_genera_slots_en_el_hueco():
    fecha = date.today() + timedelta(days=1)
    ahora = _aware(date.today(), time(9, 0))

    slots = calcular_slots(
        tramos_del_dia=[(time(10, 0), time(13, 0)), (time(16, 0), time(20, 0))],
        reservas_del_dia=[],
        duracion_servicio=30,
        fecha=fecha,
        ahora=ahora,
        paso=15,
    )

    inicios = [s.inicio for s in slots]
    assert _aware(fecha, time(12, 30)) in inicios
    assert all(not (time(13, 0) <= s.inicio.time() < time(16, 0)) for s in slots)


def test_reserva_ocupando_marca_slots_solapados_como_no_disponibles():
    fecha = date.today() + timedelta(days=1)
    ahora = _aware(date.today(), time(9, 0))
    reserva = (_aware(fecha, time(11, 0)), _aware(fecha, time(11, 45)))

    slots = calcular_slots(
        tramos_del_dia=[(time(10, 0), time(14, 0))],
        reservas_del_dia=[reserva],
        duracion_servicio=30,
        fecha=fecha,
        ahora=ahora,
        paso=15,
    )

    por_inicio = {s.inicio.time(): s.disponible for s in slots}

    assert por_inicio[time(10, 45)] is False
    assert por_inicio[time(11, 0)] is False
    assert por_inicio[time(11, 15)] is False
    assert por_inicio[time(11, 30)] is False

    assert por_inicio[time(10, 30)] is True
    assert por_inicio[time(11, 45)] is True


def test_filtro_de_hoy_descarta_slots_anteriores_a_ahora():
    hoy = date.today()
    ahora = _aware(hoy, time(11, 30))

    slots = calcular_slots(
        tramos_del_dia=[(time(10, 0), time(18, 0))],
        reservas_del_dia=[],
        duracion_servicio=30,
        fecha=hoy,
        ahora=ahora,
        paso=15,
    )

    assert all(s.inicio >= ahora for s in slots)
    assert slots[0].inicio == ahora


def test_fecha_pasada_devuelve_lista_vacia():
    hoy = date.today()
    ayer = hoy - timedelta(days=1)
    ahora = _aware(hoy, time(9, 0))

    slots = calcular_slots(
        tramos_del_dia=[(time(10, 0), time(18, 0))],
        reservas_del_dia=[],
        duracion_servicio=30,
        fecha=ayer,
        ahora=ahora,
        paso=15,
    )

    assert slots == []


def test_negocio_cerrado_sin_tramos_devuelve_lista_vacia():
    fecha = date.today() + timedelta(days=1)
    ahora = _aware(date.today(), time(9, 0))

    slots = calcular_slots(
        tramos_del_dia=[],
        reservas_del_dia=[],
        duracion_servicio=30,
        fecha=fecha,
        ahora=ahora,
        paso=15,
    )

    assert slots == []


def test_servicio_mas_largo_que_el_tramo_devuelve_lista_vacia():
    fecha = date.today() + timedelta(days=1)
    ahora = _aware(date.today(), time(9, 0))

    slots = calcular_slots(
        tramos_del_dia=[(time(10, 0), time(12, 0))],
        reservas_del_dia=[],
        duracion_servicio=300,
        fecha=fecha,
        ahora=ahora,
        paso=15,
    )

    assert slots == []


def test_antelacion_minima_empuja_el_primer_slot_disponible():
    hoy = date.today()
    ahora = _aware(hoy, time(11, 30))

    slots = calcular_slots(
        tramos_del_dia=[(time(10, 0), time(18, 0))],
        reservas_del_dia=[],
        duracion_servicio=30,
        fecha=hoy,
        ahora=ahora,
        paso=15,
        antelacion_minima=60,
    )

    assert slots[0].inicio == _aware(hoy, time(12, 30))
    assert _aware(hoy, time(11, 45)) not in [s.inicio for s in slots]


def test_paso_cero_levanta_value_error():
    fecha = date.today() + timedelta(days=1)
    ahora = _aware(date.today(), time(9, 0))

    with pytest.raises(ValueError):
        calcular_slots(
            tramos_del_dia=[(time(10, 0), time(18, 0))],
            reservas_del_dia=[],
            duracion_servicio=30,
            fecha=fecha,
            ahora=ahora,
            paso=0,
        )


def test_duracion_servicio_cero_levanta_value_error():
    fecha = date.today() + timedelta(days=1)
    ahora = _aware(date.today(), time(9, 0))

    with pytest.raises(ValueError):
        calcular_slots(
            tramos_del_dia=[(time(10, 0), time(18, 0))],
            reservas_del_dia=[],
            duracion_servicio=0,
            fecha=fecha,
            ahora=ahora,
            paso=15,
        )
