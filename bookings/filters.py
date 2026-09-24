from datetime import datetime, time, timedelta

import django_filters
from django.utils import timezone

from .models import Booking


def _medianoche_local(fecha):
    """Primer instante de `fecha` como datetime AWARE en la zona de Django.

    La zona se lee de timezone.get_current_timezone() (o sea TIME_ZONE, o la
    que esté activada en el request), nunca UTC ni naive: date_from/date_to
    son fechas que el usuario piensa en hora de Lima, y una reserva de las
    23:30 locales cae al día siguiente en UTC.
    """
    return timezone.make_aware(
        datetime.combine(fecha, time.min), timezone.get_current_timezone()
    )


class BookingFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status")
    # Sin lookup_expr: los métodos traducen la FECHA pedida a un intervalo de
    # datetimes. Ver el comentario de cada uno.
    date_from = django_filters.DateFilter(method="filtrar_desde")
    date_to = django_filters.DateFilter(method="filtrar_hasta")

    class Meta:
        model = Booking
        fields = ["status", "date_from", "date_to"]

    # POR QUÉ UN INTERVALO Y NO __date:
    # El lookup __date es correcto (Django emite AT TIME ZONE con USE_TZ), pero
    # envuelve la columna en una expresión:
    #     (start_datetime AT TIME ZONE 'America/Lima')::date <= '2026-10-15'
    # Un b-tree sobre start_datetime no puede servir ese predicado —haría falta
    # un índice por expresión que no existe—, así que se pierden los índices
    # (business, start_datetime) y (status, start_datetime) de Booking.Meta.
    # Comparar contra datetimes deja la columna "desnuda" y el índice utilizable.

    def filtrar_desde(self, queryset, name, value):
        # Límite INCLUSIVO: 00:00 locales pertenecen a su propio día.
        return queryset.filter(start_datetime__gte=_medianoche_local(value))

    def filtrar_hasta(self, queryset, name, value):
        # Intervalo SEMI-ABIERTO: < medianoche del día siguiente, no <= algún
        # "último instante" del día pedido. Con <= habría que elegir un tope
        # (23:59:59? .999999?) y cualquier reserva posterior a ese tope dentro
        # del mismo día se perdería, porque la precisión de un timestamptz de
        # Postgres es de microsegundos. El < estricto no deja huecos.
        siguiente = value + timedelta(days=1)
        return queryset.filter(start_datetime__lt=_medianoche_local(siguiente))
