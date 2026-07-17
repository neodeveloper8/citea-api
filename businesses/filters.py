import django_filters

from .models import Business, Service


class BusinessFilter(django_filters.FilterSet):
    category = django_filters.CharFilter(field_name="category__slug")

    class Meta:
        model = Business
        fields = ["category"]


class ServiceFilter(django_filters.FilterSet):
    business = django_filters.CharFilter(field_name="business__slug")

    class Meta:
        model = Service
        fields = ["business", "is_active"]
