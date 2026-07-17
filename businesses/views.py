from django.db.models import Prefetch, Q
from django.db.models.deletion import ProtectedError
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated

from core.exceptions import ServiceHasBookings
from users.permissions import IsDueno, IsOwnerOrReadOnly

from .filters import BusinessFilter, ServiceFilter
from .models import Business, BusinessImage, Category, Service
from .serializers import (
    BusinessDetailSerializer,
    BusinessListSerializer,
    BusinessWriteSerializer,
    CategorySerializer,
    ServiceWriteSerializer,
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


class ServiceViewSet(viewsets.ModelViewSet):
    # Endpoint exclusivo del dueño: el público ya recibe los servicios
    # anidados en GET /api/businesses/<slug>/. Por eso NO hay get_permissions()
    # ramificado ni queryset público.
    serializer_class = ServiceWriteSerializer
    permission_classes = [IsAuthenticated, IsDueno, IsOwnerOrReadOnly]
    owner_field = "business.owner"  # lo lee IsOwnerOrReadOnly
    filterset_class = ServiceFilter
    search_fields = ["name"]

    def get_queryset(self):
        user = self.request.user
        # Guard: spectacular puede introspeccionar la view con un user anónimo
        # al generar el schema; sin esto, filter(business__owner=AnonymousUser) explota.
        if not user.is_authenticated:
            return Service.objects.none()
        # select_related HASTA owner (no solo business): IsOwnerOrReadOnly recorre
        # service.business.owner, y sin esto son 2 queries extra POR objeto.
        return Service.objects.filter(business__owner=user).select_related(
            "business__owner"
        )

    def perform_destroy(self, instance):
        # Pedir perdón, no permiso: el PROTECT lo garantiza la BD, no Python.
        # Un chequeo previo con .exists() tendría una ventana TOCTOU.
        try:
            instance.delete()
        except ProtectedError:
            raise ServiceHasBookings()
