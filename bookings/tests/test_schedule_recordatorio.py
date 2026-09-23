import pytest
from django_q.models import Schedule

pytestmark = pytest.mark.django_db

NOMBRE = "recordatorio-reservas-24h"


def test_el_schedule_del_recordatorio_quedo_registrado():
    """La data migration 0006 lo crea; con --create-db las migraciones corren
    y la fila tiene que existir. NO ejecuta la task ni levanta qcluster."""
    schedule = Schedule.objects.get(name=NOMBRE)

    assert schedule.func == "bookings.tasks.task_enviar_recordatorios"
    assert schedule.schedule_type == Schedule.HOURLY
    assert schedule.repeats == -1
