import logging

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from businesses.models import Business
from core.exceptions import SlotJustTaken, TransicionNoPermitida
from users.permissions import IsDueno, PuedeCancelarBooking
from .exceptions import TransicionInvalida
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

    def _transicionar_como_dueno(self, request, pk, *, metodo):
        """Transición solo-dueño, atómica y con la fila bloqueada.
        Candados: IsDueno (rol, 403) + filtro business__owner (ajena -> 404)."""
        with transaction.atomic():
            booking = get_object_or_404(
                Booking.objects.select_for_update(of=("self",)).filter(
                    business__owner=request.user
                ),
                pk=pk,
            )
            try:
                getattr(booking, metodo)()
            except TransicionInvalida as exc:
                raise TransicionNoPermitida(detail=str(exc))
        serializer = BookingReadSerializer(booking, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["post"],
        url_path="confirm",
        permission_classes=[IsAuthenticated, IsDueno],
    )
    def confirm(self, request, pk=None):
        return self._transicionar_como_dueno(request, pk, metodo="confirmar")

    @action(
        detail=True,
        methods=["post"],
        url_path="cancel",
        permission_classes=[IsAuthenticated, PuedeCancelarBooking],
    )
    def cancel(self, request, pk=None):
        """Cancela una reserva. Actor: el cliente que reservó O el dueño del
        negocio. Orígenes legales (pending/confirmed) los valida el modelo."""
        with transaction.atomic():
            booking = get_object_or_404(
                Booking.objects.select_for_update(of=("self",))
                .select_related("business")
                .filter(Q(customer=request.user) | Q(business__owner=request.user)),
                pk=pk,
            )
            self.check_object_permissions(request, booking)
            try:
                booking.cancelar()
            except TransicionInvalida as exc:
                raise TransicionNoPermitida(detail=str(exc))
        serializer = BookingReadSerializer(booking, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)
