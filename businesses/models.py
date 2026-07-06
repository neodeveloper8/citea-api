# Create your models here.
from django.db import models
from django.utils.text import slugify
from django.conf import settings
from core.models import TimeStampedModel


class Category(TimeStampedModel):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Business(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        PENDING = "pending", "Pendiente de revisión"
        APPROVED = "approved", "Aprobado"
        REJECTED = "rejected", "Rechazado"
        SUSPENDED = "suspended", "Suspendido"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="businesses",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="businesses",
    )

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)

    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    rejection_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = "Negocio"
        verbose_name_plural = "Negocios"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["category", "status"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self):
        base = slugify(self.name)
        slug = base
        counter = 2
        while Business.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{counter}"
            counter += 1
        return slug


class BusinessHours(TimeStampedModel):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Lunes"
        TUESDAY = 1, "Martes"
        WEDNESDAY = 2, "Miércoles"
        THURSDAY = 3, "Jueves"
        FRIDAY = 4, "Viernes"
        SATURDAY = 5, "Sábado"
        SUNDAY = 6, "Domingo"

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="hours",
    )
    weekday = models.IntegerField(choices=Weekday.choices)
    open_time = models.TimeField()
    close_time = models.TimeField()

    class Meta:
        verbose_name = "Horario"
        verbose_name_plural = "Horarios"
        ordering = ["weekday", "open_time"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(close_time__gt=models.F("open_time")),
                name="businesshours_close_after_open",
            ),
        ]

    def __str__(self):
        return f"{self.business.name} — {self.get_weekday_display()} {self.open_time}–{self.close_time}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.open_time and self.close_time and self.close_time <= self.open_time:
            raise ValidationError(
                "La hora de cierre debe ser posterior a la de apertura."
            )


class Service(TimeStampedModel):
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="services",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveSmallIntegerField(
        help_text="Duración del servicio en minutos.",
    )
    price = models.DecimalField(max_digits=8, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Servicio"
        verbose_name_plural = "Servicios"
        ordering = ["business", "name"]

    def __str__(self):
        return f"{self.name} ({self.business.name})"


class BusinessImage(TimeStampedModel):
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="images",
    )
    public_id = models.CharField(max_length=255)
    image_url = models.URLField(max_length=500)
    alt_text = models.CharField(max_length=150, blank=True)
    is_cover = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Imagen de negocio"
        verbose_name_plural = "Imágenes de negocio"
        ordering = ["business", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["business"],
                condition=models.Q(is_cover=True),
                name="one_cover_per_business",
            ),
        ]

    def __str__(self):
        return f"Imagen de {self.business.name} ({self.public_id})"
