from rest_framework import serializers

from bookings.models import Review
from bookings.serializers import PublicReviewSerializer

from .models import Business, BusinessHours, BusinessImage, Category, Service


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "order"]


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ["id", "name", "description", "duration_minutes", "price"]


class BusinessHoursSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessHours
        fields = ["id", "weekday", "open_time", "close_time"]


class BusinessImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessImage
        fields = ["id", "image_url", "alt_text", "is_cover", "order"]


class BusinessListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    cover_image = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = ["id", "slug", "name", "category", "address", "cover_image"]

    def get_cover_image(self, obj):
        # "cover" viene del Prefetch(to_attr="cover") de la view: es una LISTA (0 o 1 elem).
        # getattr con default por si el serializer se usa sin ese prefetch.
        cover = getattr(obj, "cover", None)
        if cover:
            return BusinessImageSerializer(cover[0]).data
        return None


class BusinessDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    services = ServiceSerializer(many=True, read_only=True)
    hours = BusinessHoursSerializer(many=True, read_only=True)
    images = BusinessImageSerializer(many=True, read_only=True)
    rating_avg = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()
    reviews = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = [
            "id",
            "slug",
            "name",
            "category",
            "description",
            "address",
            "phone",
            "whatsapp",
            "email",
            "latitude",
            "longitude",
            "services",
            "hours",
            "images",
            "rating_avg",
            "rating_count",
            "reviews",
        ]

    def get_rating_avg(self, obj):
        # Anotado en BusinessViewSet.get_queryset() (rama retrieve). El
        # getattr con default cubre el caso de usar este serializer sin esa
        # anotación (ej. en un test o shell que no pase por la view).
        avg = getattr(obj, "rating_avg_ann", None)
        return round(avg, 1) if avg is not None else None

    def get_rating_count(self, obj):
        return getattr(obj, "rating_count_ann", 0)

    def get_reviews(self, obj):
        qs = (
            Review.objects.filter(booking__business=obj)
            .select_related("booking__customer", "response")
            .order_by("-created_at")[:10]
        )
        return PublicReviewSerializer(qs, many=True, context=self.context).data


class ServiceWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = [
            "id",
            "business",
            "name",
            "description",
            "duration_minutes",
            "price",
            "is_active",
        ]
        read_only_fields = ["id"]

    def validate_business(self, value):
        # CRÍTICO: 'business' es escribible (el dueño elige cuál de SUS negocios).
        # IsOwnerOrReadOnly NO cubre esto: en un POST no hay objeto todavía,
        # así que has_object_permission nunca corre. Sin esta validación, un dueño
        # podría crear servicios dentro del negocio de otro.
        if value.owner != self.context["request"].user:
            raise serializers.ValidationError(
                "No podés crear servicios en un negocio que no es tuyo."
            )
        return value


class BusinessHoursListSerializer(serializers.ListSerializer):
    def validate(self, attrs):
        # attrs es la LISTA completa. Acá validamos ENTRE elementos: el
        # CheckConstraint del modelo solo garantiza close>open por fila, pero
        # nada impide mandar 09:00-13:00 y 11:00-15:00 el mismo día (se pisan).
        from collections import defaultdict

        por_dia = defaultdict(list)
        for item in attrs:
            por_dia[item["weekday"]].append(item)

        for weekday, franjas in por_dia.items():
            franjas.sort(key=lambda f: f["open_time"])
            for previa, actual in zip(franjas, franjas[1:]):
                if actual["open_time"] < previa["close_time"]:
                    raise serializers.ValidationError(
                        f"Hay franjas horarias que se solapan en el día {weekday}."
                    )
        return attrs


class BusinessHoursWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessHours
        fields = ["weekday", "open_time", "close_time"]
        list_serializer_class = BusinessHoursListSerializer

    def validate(self, attrs):
        # Réplica del CheckConstraint: el clean() del modelo NO corre vía DRF,
        # y bulk_create tampoco lo llama. Sin esto, el error saldría como
        # IntegrityError (500) en vez de un 400 legible.
        if attrs["close_time"] <= attrs["open_time"]:
            raise serializers.ValidationError(
                "La hora de cierre debe ser posterior a la de apertura."
            )
        return attrs


class BusinessImageWriteSerializer(serializers.ModelSerializer):
    # 'image' NO es un campo del modelo: es un canal de ENTRADA puro.
    # Entra el archivo -> se sube a Cloudinary -> de la respuesta salen
    # public_id e image_url, que sí se persisten. write_only: nunca sale.
    image = serializers.ImageField(write_only=True)

    class Meta:
        model = BusinessImage
        fields = [
            "id",
            "business",
            "image",
            "public_id",
            "image_url",
            "alt_text",
            "is_cover",
            "order",
        ]
        # public_id/image_url read_only: si el cliente pudiera mandarlos,
        # apuntaría los registros a cualquier URL de internet.
        read_only_fields = ["id", "public_id", "image_url"]

    def validate_business(self, value):
        # Mismo hueco que en Services: IsOwnerOrReadOnly no cubre el POST
        # (no hay objeto todavía, has_object_permission nunca corre).
        if value.owner != self.context["request"].user:
            raise serializers.ValidationError(
                "No podés subir imágenes a un negocio que no es tuyo."
            )
        return value


class BusinessImageUpdateSerializer(serializers.ModelSerializer):
    # El archivo NO se reemplaza en un PATCH: para cambiar la foto,
    # se borra y se sube otra. Evita huérfanos y URLs rotas.
    class Meta:
        model = BusinessImage
        fields = ["id", "public_id", "image_url", "alt_text", "is_cover", "order"]
        read_only_fields = ["id", "public_id", "image_url"]


class BusinessWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = [
            "id",
            "slug",
            "name",
            "category",
            "description",
            "address",
            "phone",
            "whatsapp",
            "email",
            "latitude",
            "longitude",
        ]
        read_only_fields = ["id", "slug"]


class SlotSerializer(serializers.Serializer):
    inicio = serializers.DateTimeField()
    fin = serializers.DateTimeField()
    disponible = serializers.BooleanField()
