import logging

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from businesses.models import Business
from core.exceptions import (
    ReviewDuplicada,
    RespuestaDuplicada,
    SlotTaken,
    TransicionNoPermitida,
)
from users.permissions import IsDueno, PuedeCancelarBooking
from .emails import (
    email_reserva_cancelada,
    email_reserva_completada,
    email_reserva_confirmada,
)
from .exceptions import TransicionInvalida
from .exports import generar_csv, recolectar_clientes
from .filters import BookingFilter
from .models import Booking, Review, ReviewResponse
from .serializers import (
    BookingCreateSerializer,
    BookingReadSerializer,
    DirectBookingSerializer,
    OwnerReviewSerializer,
    ReviewCreateSerializer,
    ReviewReadSerializer,
    ReviewResponseCreateSerializer,
    ReviewResponseReadSerializer,
)

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
                raise SlotTaken()
            raise

    def _transicionar_como_dueno(self, request, pk, *, metodo, email_fn=None):
        """Transición solo-dueño, atómica y con la fila bloqueada.
        Candados: IsDueno (rol, 403) + filtro business__owner (ajena -> 404)."""
        with transaction.atomic():
            booking = get_object_or_404(
                Booking.objects.select_for_update(of=("self",))
                .select_related("business", "service", "customer")
                .filter(business__owner=request.user),
                pk=pk,
            )
            try:
                getattr(booking, metodo)()
            except TransicionInvalida as exc:
                raise TransicionNoPermitida(detail=str(exc))
            if email_fn is not None:
                transaction.on_commit(lambda: email_fn(booking))
        serializer = BookingReadSerializer(booking, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["post"],
        url_path="confirm",
        permission_classes=[IsAuthenticated, IsDueno],
    )
    def confirm(self, request, pk=None):
        return self._transicionar_como_dueno(
            request, pk, metodo="confirmar", email_fn=email_reserva_confirmada
        )

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
                .select_related("business", "service", "customer")
                .filter(Q(customer=request.user) | Q(business__owner=request.user)),
                pk=pk,
            )
            self.check_object_permissions(request, booking)
            try:
                booking.cancelar()
            except TransicionInvalida as exc:
                raise TransicionNoPermitida(detail=str(exc))
            transaction.on_commit(lambda: email_reserva_cancelada(booking))
        serializer = BookingReadSerializer(booking, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["post"],
        url_path="complete",
        permission_classes=[IsAuthenticated, IsDueno],
    )
    def complete(self, request, pk=None):
        return self._transicionar_como_dueno(
            request, pk, metodo="completar", email_fn=email_reserva_completada
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="no-show",
        permission_classes=[IsAuthenticated, IsDueno],
    )
    def no_show(self, request, pk=None):
        return self._transicionar_como_dueno(request, pk, metodo="marcar_no_show")

    @action(
        detail=False,
        methods=["get"],
        url_path=r"business/(?P<slug>[\w-]+)/export",
        permission_classes=[IsAuthenticated, IsDueno],
    )
    def export_clients(self, request, slug=None):
        # scopeo por owner: si el slug es de otro dueño, no hay negocio -> 404.
        # (acá SÍ 404, porque necesitamos el objeto business concreto para el
        #  filename y para filtrar; usamos el patrón Variante A del propio
        #  BookingViewSet.business)
        business = get_object_or_404(Business, slug=slug)
        if business.owner != request.user:
            raise Http404()
        filas = recolectar_clientes(business)
        contenido = generar_csv(filas)
        resp = HttpResponse(contenido, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = (
            f'attachment; filename="clientes_{business.slug}.csv"'
        )
        return resp

    @action(
        detail=False,
        methods=["post"],
        url_path="direct",
        permission_classes=[IsAuthenticated, IsDueno],
    )
    def direct(self, request):
        write = DirectBookingSerializer(data=request.data, context={"request": request})
        write.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                booking = write.save()
        except IntegrityError as exc:
            if "excluir_reservas_solapadas" in str(exc):
                raise SlotTaken()
            raise
        read = BookingReadSerializer(booking, context={"request": request})
        return Response(read.data, status=status.HTTP_201_CREATED)


class ReviewViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = Review.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = ReviewCreateSerializer

    def create(self, request, *args, **kwargs):
        write = self.get_serializer(data=request.data)
        write.is_valid(raise_exception=True)
        booking = write.validated_data["booking"]
        try:
            # El atomic() es obligatorio para el except de abajo: en Postgres
            # una violación de constraint aborta la transacción entera, y
            # cualquier consulta posterior muere con TransactionManagementError
            # ("You can't execute queries until the end of the 'atomic' block").
            # Envolviendo el save() en su propio bloque, el rollback se limita
            # a él y la conexión queda usable para hacer el recheck.
            with transaction.atomic():
                review = write.save()
        except IntegrityError:
            # No asumimos QUÉ constraint falló: preguntamos. Si la review
            # existe, perdimos la carrera contra otro request -> 409. Si no
            # existe, el IntegrityError es otra cosa (un bug real) y se
            # re-lanza para que dé 500 en vez de quedar disfrazado de
            # duplicado.
            if Review.objects.filter(booking=booking).exists():
                raise ReviewDuplicada()
            raise
        read = ReviewReadSerializer(review, context={"request": request})
        return Response(read.data, status=status.HTTP_201_CREATED)

    @action(
        detail=False,
        methods=["get"],
        url_path="business/(?P<slug>[^/.]+)",
        permission_classes=[IsAuthenticated, IsDueno],
    )
    def business(self, request, slug=None):
        # Si el negocio no es del dueño, el queryset sale vacío -> lista
        # vacía, no 404. Es lista, no detalle: no filtramos existencia de
        # un objeto puntual.
        qs = (
            Review.objects.filter(
                booking__business__slug=slug,
                booking__business__owner=request.user,
            )
            .select_related("booking__customer", "response")
            .order_by("-created_at")
        )
        page = self.paginate_queryset(qs)
        ser = OwnerReviewSerializer(page or qs, many=True, context={"request": request})
        return (
            self.get_paginated_response(ser.data)
            if page is not None
            else Response(ser.data)
        )


class ReviewResponseViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = ReviewResponse.objects.all()
    permission_classes = [IsAuthenticated, IsDueno]
    serializer_class = ReviewResponseCreateSerializer

    def create(self, request, *args, **kwargs):
        write = self.get_serializer(data=request.data)
        write.is_valid(raise_exception=True)
        review = write.validated_data["review"]
        try:
            # Mismo motivo que en ReviewViewSet: sin este atomic(), el recheck
            # del except correría sobre una transacción ya abortada.
            with transaction.atomic():
                resp = write.save()
        except IntegrityError:
            if ReviewResponse.objects.filter(review=review).exists():
                raise RespuestaDuplicada()
            raise
        read = ReviewResponseReadSerializer(resp, context={"request": request})
        return Response(read.data, status=status.HTTP_201_CREATED)
