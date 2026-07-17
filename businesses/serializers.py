from rest_framework import serializers

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
        ]


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
