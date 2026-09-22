# Create your models here.
# bookings/models.py
from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import (
    DateTimeRangeField,
    RangeBoundary,
    RangeOperators,
)
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Func, Q

from core.models import TimeStampedModel
from businesses.models import Business, Service


class TsTzRange(Func):
    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class Booking(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        CONFIRMED = "confirmed", "Confirmada"
        CANCELLED = "cancelled", "Cancelada"
        COMPLETED = "completed", "Completada"
        NO_SHOW = "no_show", "No asistió"

    class Source(models.TextChoices):
        MARKETPLACE = "marketplace", "Marketplace"
        DIRECT = "direct", "Directa"

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bookings",
        null=True,
        blank=True,
    )
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="bookings",
    )

    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()

    price_at_booking = models.DecimalField(max_digits=8, decimal_places=2)
    duration_at_booking = models.PositiveSmallIntegerField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.MARKETPLACE,
    )
    is_first_booking_for_business = models.BooleanField(default=False)

    customer_note = models.TextField(blank=True)

    # Cliente telefónico (sin cuenta): mutuamente excluyente con customer,
    # forzado por la CheckConstraint booking_customer_xor_guest en Meta.
    guest_name = models.CharField(max_length=150, blank=True, default="")
    guest_phone = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        verbose_name = "Reserva"
        verbose_name_plural = "Reservas"
        ordering = ["-start_datetime"]
        indexes = [
            models.Index(fields=["business", "start_datetime"]),
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_datetime__gt=models.F("start_datetime")),
                name="booking_end_after_start",
            ),
            models.CheckConstraint(
                condition=(
                    (models.Q(customer__isnull=False) & models.Q(guest_name=""))
                    | (models.Q(customer__isnull=True) & ~models.Q(guest_name=""))
                ),
                name="booking_customer_xor_guest",
            ),
            ExclusionConstraint(
                name="excluir_reservas_solapadas",
                expressions=(
                    (
                        TsTzRange("start_datetime", "end_datetime", RangeBoundary()),
                        RangeOperators.OVERLAPS,
                    ),
                    ("business", RangeOperators.EQUAL),
                ),
                condition=Q(status__in=["pending", "confirmed"]),
            ),
        ]

    def __str__(self):
        return f"{self.customer.email} → {self.business.name} ({self.start_datetime:%Y-%m-%d %H:%M})"

    def clean(self):
        if (
            self.start_datetime
            and self.end_datetime
            and self.end_datetime <= self.start_datetime
        ):
            raise ValidationError("El fin de la reserva debe ser posterior al inicio.")
        if (
            self.service_id
            and self.business_id
            and self.service.business_id != self.business_id
        ):
            raise ValidationError("El servicio no pertenece al negocio de la reserva.")

    def _transicionar(self, *, accion, permitidos, destino):
        from bookings.exceptions import TransicionInvalida

        if self.status not in permitidos:
            raise TransicionInvalida(
                estado_actual=self.status, accion=accion, permitidos=permitidos
            )
        self.status = destino
        self.save(update_fields=["status", "updated_at"])

    def confirmar(self):
        self._transicionar(
            accion="confirmar",
            permitidos={self.Status.PENDING},
            destino=self.Status.CONFIRMED,
        )

    def cancelar(self):
        self._transicionar(
            accion="cancelar",
            permitidos={self.Status.PENDING, self.Status.CONFIRMED},
            destino=self.Status.CANCELLED,
        )

    def completar(self):
        self._transicionar(
            accion="completar",
            permitidos={self.Status.CONFIRMED},
            destino=self.Status.COMPLETED,
        )

    def marcar_no_show(self):
        self._transicionar(
            accion="marcar_no_show",
            permitidos={self.Status.CONFIRMED},
            destino=self.Status.NO_SHOW,
        )


class Review(TimeStampedModel):
    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name="review",
    )
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)

    class Meta:
        verbose_name = "Reseña"
        verbose_name_plural = "Reseñas"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rating__gte=1) & models.Q(rating__lte=5),
                name="review_rating_between_1_and_5",
            ),
        ]

    def __str__(self):
        return f"{self.rating}★ — {self.booking.business.name}"

    def clean(self):
        if self.booking_id and self.booking.status != Booking.Status.COMPLETED:
            raise ValidationError("Solo se puede reseñar una reserva completada.")


class ReviewResponse(TimeStampedModel):
    review = models.OneToOneField(
        Review,
        on_delete=models.CASCADE,
        related_name="response",
    )
    body = models.TextField()

    class Meta:
        verbose_name = "Respuesta a reseña"
        verbose_name_plural = "Respuestas a reseñas"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Respuesta a {self.review}"
