import logging

import cloudinary.uploader
from django.db import transaction
from django.db.models import Prefetch, Q
from django.db.models.deletion import ProtectedError
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from core.exceptions import ServiceHasBookings
from users.permissions import IsDueno, IsOwnerOrReadOnly

from .filters import BusinessFilter, BusinessImageFilter, ServiceFilter
from .models import Business, BusinessHours, BusinessImage, Category, Service
from .serializers import (
    BusinessDetailSerializer,
    BusinessHoursSerializer,
    BusinessHoursWriteSerializer,
    BusinessImageUpdateSerializer,
    BusinessImageWriteSerializer,
    BusinessListSerializer,
    BusinessWriteSerializer,
    CategorySerializer,
    ServiceWriteSerializer,
)

logger = logging.getLogger(__name__)


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
        if self.action in ("update", "partial_update", "hours"):
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
        if self.action in ("update", "partial_update", "hours"):
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

    @extend_schema(
        request=BusinessHoursWriteSerializer(many=True),
        responses=BusinessHoursSerializer(many=True),
    )
    @action(detail=True, methods=["put"], url_path="hours")
    def hours(self, request, slug=None):
        # get_object() hace DOS cosas: busca en get_queryset() (404 si no es tuyo)
        # y dispara check_object_permissions() -> IsOwnerOrReadOnly. Dos candados.
        business = self.get_object()

        serializer = BusinessHoursWriteSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        # Reemplazo total: borrar y recrear. ATÓMICO es obligatorio: entre el
        # delete y el create hay un instante sin horarios; si el create falla,
        # sin transacción le borrás el horario al dueño y no hay vuelta atrás.
        with transaction.atomic():
            business.hours.all().delete()
            BusinessHours.objects.bulk_create(
                [
                    BusinessHours(business=business, **item)
                    for item in serializer.validated_data
                ]
            )

        return Response(BusinessHoursSerializer(business.hours.all(), many=True).data)


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


class BusinessImageViewSet(viewsets.ModelViewSet):
    # Endpoint exclusivo del dueño: el público ya recibe las imágenes
    # anidadas en GET /api/businesses/<slug>/.
    permission_classes = [IsAuthenticated, IsDueno, IsOwnerOrReadOnly]
    owner_field = "business.owner"
    parser_classes = [MultiPartParser, FormParser]  # explícito: recibe archivos
    filterset_class = BusinessImageFilter

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return BusinessImageUpdateSerializer
        return BusinessImageWriteSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return BusinessImage.objects.none()
        # select_related HASTA owner: IsOwnerOrReadOnly recorre image.business.owner
        return BusinessImage.objects.filter(business__owner=user).select_related(
            "business__owner"
        )

    def perform_create(self, serializer):
        business = serializer.validated_data["business"]
        # 'image' no es campo del modelo: hay que sacarlo antes del save()
        archivo = serializer.validated_data.pop("image")

        result = cloudinary.uploader.upload(
            archivo, folder=f"citea/businesses/{business.id}"
        )
        try:
            with transaction.atomic():
                # Degradar la portada anterior: el UniqueConstraint parcial
                # permite UNA sola con is_cover=True. Sin esto -> IntegrityError (500).
                if serializer.validated_data.get("is_cover"):
                    business.images.filter(is_cover=True).update(is_cover=False)
                serializer.save(
                    public_id=result["public_id"],
                    image_url=result["secure_url"],
                )
        except Exception:
            # ACCIÓN COMPENSATORIA: transaction.atomic() hace rollback de POSTGRES,
            # NO de Cloudinary. Sin esto, el archivo queda huérfano allá para siempre.
            cloudinary.uploader.destroy(result["public_id"])
            raise

    def perform_update(self, serializer):
        with transaction.atomic():
            if serializer.validated_data.get("is_cover"):
                serializer.instance.business.images.filter(is_cover=True).exclude(
                    pk=serializer.instance.pk
                ).update(is_cover=False)
            serializer.save()

    def perform_destroy(self, instance):
        public_id = instance.public_id
        # ORDEN DELIBERADO: la BD primero. Si Cloudinary falla después, queda un
        # huérfano invisible (solo ocupa espacio). Al revés quedaría una fila
        # apuntando a una URL muerta -> imagen rota en producción.
        instance.delete()
        try:
            cloudinary.uploader.destroy(public_id)
        except Exception:
            # No rompemos la respuesta: desde el punto de vista del dueño la
            # imagen YA desapareció de su galería. La acción tuvo éxito.
            logger.warning("Huérfano en Cloudinary: %s", public_id, exc_info=True)
