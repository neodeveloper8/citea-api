from django.db.models import Prefetch
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from .filters import BusinessFilter
from .models import Business, BusinessImage, Category, Service
from .serializers import (
    BusinessDetailSerializer,
    BusinessListSerializer,
    CategorySerializer,
)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Category.objects.filter(is_active=True).order_by("order")


class BusinessViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    lookup_field = "slug"
    filterset_class = BusinessFilter
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return BusinessDetailSerializer
        return BusinessListSerializer

    def get_queryset(self):
        qs = Business.objects.filter(status="approved").select_related("category")

        if self.action == "retrieve":
            return qs.prefetch_related(
                Prefetch("services", queryset=Service.objects.filter(is_active=True)),
                "hours",
                "images",
            )

        # list: solo la portada, en UNA query extra (evita N+1)
        return qs.prefetch_related(
            Prefetch(
                "images",
                queryset=BusinessImage.objects.filter(is_cover=True),
                to_attr="cover",
            )
        )
