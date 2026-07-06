# Create your models here.
# bookings/models.py
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import TimeStampedModel
from businesses.models import Business, Service


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
