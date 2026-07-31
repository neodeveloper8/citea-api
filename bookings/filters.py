import django_filters

from .models import Booking


class BookingFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status")
    date_from = django_filters.DateFilter(
        field_name="start_datetime", lookup_expr="date__gte"
    )
    date_to = django_filters.DateFilter(
        field_name="start_datetime", lookup_expr="date__lte"
    )

    class Meta:
        model = Booking
        fields = ["status", "date_from", "date_to"]
