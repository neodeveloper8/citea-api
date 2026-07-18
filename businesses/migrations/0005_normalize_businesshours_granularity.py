from datetime import time

from django.db import migrations


def truncate_to_quarter_hour(value):
    minute = (value.minute // 15) * 15
    return time(hour=value.hour, minute=minute, second=0, microsecond=0)


def normalize_businesshours_times(apps, schema_editor):
    BusinessHours = apps.get_model("businesses", "BusinessHours")

    for hours in BusinessHours.objects.all():
        update_fields = []

        normalized_open = truncate_to_quarter_hour(hours.open_time)
        if normalized_open != hours.open_time:
            hours.open_time = normalized_open
            update_fields.append("open_time")

        normalized_close = truncate_to_quarter_hour(hours.close_time)
        if normalized_close != hours.close_time:
            hours.close_time = normalized_close
            update_fields.append("close_time")

        if update_fields:
            hours.save(update_fields=update_fields)


def reverse_noop(apps, schema_editor):
    # No reversible: truncar segundos y redondear minutos pierde información
    # (el valor original no puede reconstruirse), así que el reverse es un no-op.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("businesses", "0004_businessimage"),
    ]

    operations = [
        migrations.RunPython(normalize_businesshours_times, reverse_noop),
    ]
