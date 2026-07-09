import django_filters

from .models import Business


class BusinessFilter(django_filters.FilterSet):
    category = django_filters.CharFilter(field_name="category__slug")

    class Meta:
        model = Business
        fields = ["category"]
