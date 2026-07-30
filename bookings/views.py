import logging

from django.db import IntegrityError, transaction
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from core.exceptions import SlotJustTaken
from .models import Booking
from .serializers import BookingCreateSerializer

logger = logging.getLogger(__name__)


class BookingViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = BookingCreateSerializer
    permission_classes = [IsAuthenticated]
    queryset = Booking.objects.all()

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
