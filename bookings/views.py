import logging

from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from businesses.models import Business
from core.exceptions import SlotJustTaken
from users.permissions import IsDueno
from .filters import BookingFilter
from .models import Booking
from .serializers import BookingCreateSerializer, BookingReadSerializer

logger = logging.getLogger(__name__)


class BookingViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = BookingCreateSerializer
    permission_classes = [IsAuthenticated]
    queryset = Booking.objects.all()
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = BookingFilter
    ordering_fields = ["start_datetime"]
    ordering = ["start_datetime"]

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        qs = (
            Booking.objects.filter(customer=request.user)
            .select_related("business", "service", "customer")
            .order_by("start_datetime")
        )
        filtered = self.filter_queryset(qs)
        page = self.paginate_queryset(filtered)
        if page is not None:
            serializer = BookingReadSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = BookingReadSerializer(filtered, many=True)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"business/(?P<slug>[\w-]+)",
        permission_classes=[IsAuthenticated, IsDueno],
    )
    def business(self, request, slug=None):
        business = get_object_or_404(Business, slug=slug)
        if business.owner != request.user:
            # 404, no 403: no confirmamos a un no-dueño que el negocio existe.
            raise Http404()

        qs = (
            Booking.objects.filter(business=business)
            .select_related("business", "service", "customer")
            .order_by("start_datetime")
        )
        filtered = self.filter_queryset(qs)
        page = self.paginate_queryset(filtered)
        if page is not None:
            serializer = BookingReadSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = BookingReadSerializer(filtered, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        # El candado 1 (serializer) ya validó disponibilidad. Pero entre
        # esa validación y este INSERT hay una ventana donde otro request
        # concurrente puede haber tomado el slot (race condition / TOCTOU).
        # El candado 2 (ExclusionConstraint en la BD) atrapa ese caso: el
        # INSERT viola la constraint y Postgres levanta IntegrityError.
        # Lo envolvemos en atomic() porque una violación aborta la
        # transacción en Postgres; así solo se revierte este bloque.
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError as exc:
            # Solo traducimos a 409 el solape. Otros IntegrityError son
            # bugs reales y deben propagarse (500), no esconderse.
            if "excluir_reservas_solapadas" in str(exc):
                raise SlotJustTaken()
            raise
