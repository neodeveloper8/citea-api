from django.db.models import Prefetch, Q
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated

from users.permissions import IsDueno, IsOwnerOrReadOnly

from .filters import BusinessFilter
from .models import Business, BusinessImage, Category, Service
from .serializers import (
    BusinessDetailSerializer,
    BusinessListSerializer,
    BusinessWriteSerializer,
    CategorySerializer,
)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Category.objects.filter(is_active=True).order_by("order")


class BusinessViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    lookup_field = "slug"
    filterset_class = BusinessFilter
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at"]
    ordering = ["-created_at"]

    owner_field = "owner"  # lo lee IsOwnerOrReadOnly

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), IsDueno()]
        if self.action in ("update", "partial_update"):
            return [IsAuthenticated(), IsDueno(), IsOwnerOrReadOnly()]
        return [AllowAny()]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return BusinessDetailSerializer
        if self.action in ("create", "update", "partial_update"):
            return BusinessWriteSerializer
        return BusinessListSerializer

    def get_queryset(self):
        qs = Business.objects.select_related("category")
        user = self.request.user

        # Escritura: solo los negocios del usuario (404 si no es suyo).
        if self.action in ("update", "partial_update"):
            return qs.filter(owner=user)

        # Detalle: los aprobados + los propios (para que el dueño vea su draft).
        if self.action == "retrieve":
            visible = Q(status=Business.Status.APPROVED)
            if user.is_authenticated:
                visible |= Q(owner=user)
            return qs.filter(visible).prefetch_related(
                Prefetch("services", queryset=Service.objects.filter(is_active=True)),
                "hours",
                "images",
            )

        # list (público): solo aprobados, con portada prefetcheada.
        return qs.filter(status=Business.Status.APPROVED).prefetch_related(
            Prefetch(
                "images",
                queryset=BusinessImage.objects.filter(is_cover=True),
                to_attr="cover",
            )
        )

    def perform_create(self, serializer):
        # El owner NUNCA viene del cliente: lo pone el backend.
        # status usa el default del modelo (draft).
        serializer.save(owner=self.request.user)
