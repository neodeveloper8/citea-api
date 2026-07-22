"""Motor puro de cálculo de slots de disponibilidad.

No importa Django ORM ni modelos: recibe tramos horarios y reservas ya
resueltos por el caller (la view/servicio se encarga de leer la BD).
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.utils import timezone
from zoneinfo import ZoneInfo

LIMA_TZ = ZoneInfo("America/Lima")


@dataclass
class Slot:
    inicio: datetime
    fin: datetime
    disponible: bool


def _combinar_lima(fecha: date, hora: time) -> datetime:
    return timezone.make_aware(datetime.combine(fecha, hora), LIMA_TZ)


def _se_solapan(
    a_ini: datetime, a_fin: datetime, b_ini: datetime, b_fin: datetime
) -> bool:
    return a_ini < b_fin and a_fin > b_ini


def calcular_slots(
    tramos_del_dia,
    reservas_del_dia,
    duracion_servicio,
    fecha,
    ahora,
    paso=15,
    antelacion_minima=0,
):
    if paso <= 0:
        raise ValueError("paso debe ser mayor a 0")
    if duracion_servicio <= 0:
        raise ValueError("duracion_servicio debe ser mayor a 0")

    if not tramos_del_dia:
        return []

    hoy_lima = ahora.astimezone(LIMA_TZ).date()
    if fecha < hoy_lima:
        return []

    duracion_delta = timedelta(minutes=duracion_servicio)
    paso_delta = timedelta(minutes=paso)
    limite_pasado = ahora + timedelta(minutes=antelacion_minima)
    es_hoy = fecha == hoy_lima

    slots = []
    for apertura, cierre in tramos_del_dia:
        cierre_dt = _combinar_lima(fecha, cierre)
        candidato = _combinar_lima(fecha, apertura)

        while candidato + duracion_delta <= cierre_dt:
            if es_hoy and candidato < limite_pasado:
                candidato += paso_delta
                continue

            fin = candidato + duracion_delta
            disponible = not any(
                _se_solapan(candidato, fin, r_ini, r_fin)
                for r_ini, r_fin in reservas_del_dia
            )
            slots.append(Slot(inicio=candidato, fin=fin, disponible=disponible))
            candidato += paso_delta

    slots.sort(key=lambda s: s.inicio)
    return slots
