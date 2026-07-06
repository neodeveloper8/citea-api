# bookings/admin.py
from django.contrib import admin

from .models import Booking, Review, ReviewResponse


class ReviewResponseInline(admin.StackedInline):
    model = ReviewResponse
    extra = 0
    fields = ("body",)


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer",
        "business",
        "service",
        "start_datetime",
        "status",
        "source",
    )
    list_filter = ("status", "source", "start_datetime")
    search_fields = ("customer__email", "business__name")
    autocomplete_fields = ("customer", "business", "service")
    readonly_fields = (
        "price_at_booking",
        "duration_at_booking",
        "is_first_booking_for_business",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "start_datetime"
    ordering = ("-start_datetime",)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "booking", "rating", "created_at")
    list_filter = ("rating",)
    search_fields = ("booking__business__name", "booking__customer__email")
    autocomplete_fields = ("booking",)
    readonly_fields = ("created_at", "updated_at")
    inlines = (ReviewResponseInline,)
