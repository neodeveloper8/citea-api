from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework import serializers

from businesses.models import Business, Service
from bookings.availability import calcular_slots
from bookings.models import Booking, Review, ReviewResponse
from bookings.restrictions import esta_restringido
from core.exceptions import ClienteRestringido
from users.models import User

LIMA_TZ = ZoneInfo("America/Lima")


class BookingCreateSerializer(serializers.ModelSerializer):
    business = serializers.PrimaryKeyRelatedField(
        queryset=Business.objects.filter(status=Business.Status.APPROVED)
    )
    service = serializers.PrimaryKeyRelatedField(
        queryset=Service.objects.filter(is_active=True)
    )

    class Meta:
        model = Booking
        fields = [
            "id",
            "customer",
            "business",
            "service",
            "start_datetime",
            "end_datetime",
            "price_at_booking",
            "duration_at_booking",
            "status",
            "source",
            "is_first_booking_for_business",
            "customer_note",
        ]
        read_only_fields = [
            "id",
            "customer",
            "end_datetime",
            "price_at_booking",
            "duration_at_booking",
            "status",
            "source",
            "is_first_booking_for_business",
        ]

    def validate(self, attrs):
        request = self.context["request"]
        business = attrs["business"]
        service = attrs["service"]
        start_datetime = attrs["start_datetime"]

        if esta_restringido(
            customer=request.user, business=business, ahora=timezone.now()
        ):
            raise ClienteRestringido()

        if service.business_id != business.id:
            raise serializers.ValidationError(
                {"service": "El servicio no pertenece al negocio indicado."}
            )
        if not service.is_active:
            raise serializers.ValidationError(
                {"service": "El servicio no está activo."}
            )

        # Reconstruimos la misma grilla que expone GET availability para
        # validar que el horario pedido sea efectivamente uno de los slots
        # que el cliente pudo haber visto (evita reservas "a mano" fuera
        # de grilla o sobre huecos ya ocupados).
        inicio_lima = start_datetime.astimezone(LIMA_TZ)
        fecha = inicio_lima.date()

        tramos = [
            (h.open_time, h.close_time)
            for h in business.hours.filter(weekday=fecha.weekday()).order_by(
                "open_time"
            )
        ]

        inicio_dia = timezone.make_aware(datetime.combine(fecha, time.min), LIMA_TZ)
        fin_dia = inicio_dia + timedelta(days=1)
        reservas = [
            (b.start_datetime.astimezone(LIMA_TZ), b.end_datetime.astimezone(LIMA_TZ))
            for b in Booking.objects.filter(
                business=business,
                status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED],
                start_datetime__lt=fin_dia,
                end_datetime__gt=inicio_dia,
            )
        ]

        slots = calcular_slots(
            tramos_del_dia=tramos,
            reservas_del_dia=reservas,
            duracion_servicio=service.duration_minutes,
            fecha=fecha,
            ahora=timezone.now(),
            paso=15,
        )

        # Comparación exacta (no "cabe dentro de"): el slot elegido debe
        # calzar con el inicio de un slot disponible tal cual lo devuelve
        # el motor, para no aceptar horarios arbitrarios entre pasos de 15 min.
        slot_elegido = next(
            (s for s in slots if s.disponible and s.inicio == inicio_lima),
            None,
        )
        if slot_elegido is None:
            raise serializers.ValidationError(
                {"start_datetime": "Ese horario no está disponible."}
            )

        attrs["_slot"] = slot_elegido
        return attrs

    def create(self, validated_data):
        slot = validated_data.pop("_slot")
        service = validated_data["service"]
        business = validated_data["business"]

        # Snapshot: price/duration quedan congelados al momento de reservar,
        # así un cambio posterior de precio o duración del servicio no
        # altera reservas ya creadas.
        return Booking.objects.create(
            customer=self.context["request"].user,
            business=business,
            service=service,
            start_datetime=validated_data["start_datetime"],
            end_datetime=slot.fin,
            price_at_booking=service.price,
            duration_at_booking=service.duration_minutes,
            customer_note=validated_data.get("customer_note", ""),
            is_first_booking_for_business=not Booking.objects.filter(
                business=business
            ).exists(),
        )


class DirectBookingSerializer(serializers.ModelSerializer):
    """Reserva 'direct' que carga el DUEÑO por un cliente sin cuenta (guest,
    telefónico). Deliberadamente separado de BookingCreateSerializer: sin
    customer, sin candado de restricción por no-shows, sin match contra la
    grilla de disponibilidad (el dueño mete el horario que quiera). La
    ExclusionConstraint de la BD sigue protegiendo el anti-solape igual."""

    class Meta:
        model = Booking
        fields = [
            "id",
            "business",
            "service",
            "start_datetime",
            "guest_name",
            "guest_phone",
        ]
        # NO exponer customer/source/status/end_datetime/price/duration:
        # los pone el backend.

    def validate_guest_name(self, value):
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError("El nombre del cliente es obligatorio.")
        return v

    def validate_business(self, business):
        # candado de ownership: el dueño solo carga direct en SU negocio.
        request = self.context["request"]
        if business.owner_id != request.user.id:
            raise serializers.ValidationError("No es tu negocio.")
        return business

    def validate(self, attrs):
        # service pertenece al business + activo (como el de cliente).
        # NO valida grilla ni restricción: el dueño mete el horario que quiera.
        service = attrs["service"]
        business = attrs["business"]
        if service.business_id != business.id:
            raise serializers.ValidationError(
                {"service": "El servicio no pertenece a este negocio."}
            )
        if not service.is_active:
            raise serializers.ValidationError(
                {"service": "El servicio no está activo."}
            )
        return attrs

    def create(self, validated_data):
        service = validated_data["service"]
        start = validated_data["start_datetime"]
        # snapshot igual que el flujo normal:
        validated_data["end_datetime"] = start + timedelta(
            minutes=service.duration_minutes
        )
        validated_data["price_at_booking"] = service.price
        validated_data["duration_at_booking"] = service.duration_minutes
        # autoridad del backend:
        validated_data["customer"] = None
        validated_data["source"] = Booking.Source.DIRECT
        validated_data["status"] = Booking.Status.CONFIRMED
        return Booking.objects.create(**validated_data)


class BookingBusinessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = ["slug", "name"]


class BookingServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ["id", "name", "duration_minutes"]


class BookingCustomerSerializer(serializers.ModelSerializer):
    # Todos los campos son de solo lectura: este serializer nunca escribe al
    # User, solo lo expone dentro de una reserva (ver users/models.py).
    class Meta:
        model = User
        fields = ["id", "email", "phone", "full_name"]


class BookingReadSerializer(serializers.ModelSerializer):
    business = BookingBusinessSerializer(read_only=True)
    service = BookingServiceSerializer(read_only=True)
    customer = BookingCustomerSerializer(read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "start_datetime",
            "end_datetime",
            "status",
            "price_at_booking",
            "duration_at_booking",
            "customer_note",
            "business",
            "service",
            "customer",
            "guest_name",
            "guest_phone",
        ]
        read_only_fields = fields


class ReviewCreateSerializer(serializers.ModelSerializer):
    booking = serializers.PrimaryKeyRelatedField(queryset=Booking.objects.none())
    rating = serializers.IntegerField(min_value=1, max_value=5)

    class Meta:
        model = Review
        fields = ["id", "booking", "rating", "comment"]
        read_only_fields = ["id"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            self.fields["booking"].queryset = Booking.objects.filter(
                customer=request.user
            )

    def validate_booking(self, booking):
        if booking.status != Booking.Status.COMPLETED:
            raise serializers.ValidationError(
                "Solo podés reseñar una reserva completada."
            )
        if Review.objects.filter(booking=booking).exists():
            raise serializers.ValidationError(
                "Ya dejaste una reseña para esta reserva."
            )
        return booking


class ReviewReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ["id", "booking", "rating", "comment", "created_at"]
        read_only_fields = fields


class ReviewResponseCreateSerializer(serializers.ModelSerializer):
    review = serializers.PrimaryKeyRelatedField(queryset=Review.objects.none())

    class Meta:
        model = ReviewResponse
        fields = ["id", "review", "body"]
        read_only_fields = ["id"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            self.fields["review"].queryset = Review.objects.filter(
                booking__business__owner=request.user
            )

    def validate_review(self, review):
        if ReviewResponse.objects.filter(review=review).exists():
            raise serializers.ValidationError("Esta reseña ya tiene respuesta.")
        return review


class ReviewResponseReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewResponse
        fields = ["id", "review", "body", "created_at"]
        read_only_fields = fields


class PublicReviewSerializer(serializers.ModelSerializer):
    # Deliberadamente mínimo: este dato es público, sin auth. NO exponer
    # "booking" ni email/phone/nombre completo del cliente — solo el primer
    # nombre vía get_short_name (sale "" si el user legacy no tiene full_name).
    author = serializers.CharField(
        source="booking.customer.get_short_name", read_only=True
    )
    response = ReviewResponseReadSerializer(read_only=True)

    class Meta:
        model = Review
        fields = ["id", "rating", "comment", "author", "created_at", "response"]
        read_only_fields = fields


class OwnerReviewSerializer(serializers.ModelSerializer):
    response = ReviewResponseReadSerializer(read_only=True)
    customer_name = serializers.CharField(
        source="booking.customer.get_full_name", read_only=True
    )

    class Meta:
        model = Review
        fields = [
            "id",
            "booking",
            "rating",
            "comment",
            "created_at",
            "customer_name",
            "response",
        ]
        read_only_fields = fields
