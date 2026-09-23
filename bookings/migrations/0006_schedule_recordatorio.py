from django.db import migrations

NOMBRE = "recordatorio-reservas-24h"


def crear_schedule(apps, schema_editor):
    # get_or_create: idempotente. Si la migración se re-aplica sobre una BD
    # que ya tiene el schedule, no lo duplica.
    Schedule = apps.get_model("django_q", "Schedule")
    Schedule.objects.get_or_create(
        name=NOMBRE,
        defaults={
            "func": "bookings.tasks.task_enviar_recordatorios",
            "schedule_type": "H",  # Schedule.HOURLY
            "repeats": -1,  # infinito
        },
    )


def borrar_schedule(apps, schema_editor):
    Schedule = apps.get_model("django_q", "Schedule")
    Schedule.objects.filter(name=NOMBRE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0005_reminder_sent_at"),
        # OBLIGATORIA: esta data migration escribe en la tabla Schedule de
        # django_q, así que sus migraciones tienen que correr ANTES.
        ("django_q", "0019_alter_task_options_alter_ormq_key_alter_ormq_lock_and_more"),
    ]

    operations = [migrations.RunPython(crear_schedule, borrar_schedule)]
