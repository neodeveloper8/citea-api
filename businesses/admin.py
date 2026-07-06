# Register your models here.
from django.contrib import admin

from .models import (
    Category,
    Business,
    BusinessHours,
    Service,
    BusinessImage,
)


class BusinessHoursInline(admin.TabularInline):
    model = BusinessHours
    extra = 1
    ordering = ("weekday", "open_time")


class ServiceInline(admin.TabularInline):
    model = Service
    extra = 1
    fields = ("name", "duration_minutes", "price", "is_active")
    show_change_link = True


class BusinessImageInline(admin.TabularInline):
    model = BusinessImage
    extra = 1
    fields = ("image_url", "public_id", "is_cover", "order")
    readonly_fields = ("public_id",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "order", "created_at")
    list_editable = ("is_active", "order")
    list_filter = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("order", "name")


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "owner", "status", "phone", "created_at")
    list_filter = ("status", "category")
    search_fields = ("name", "owner__email", "phone")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("owner", "category")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("name",)
    inlines = (BusinessHoursInline, ServiceInline, BusinessImageInline)
    actions = ("aprobar_negocios", "rechazar_negocios")

    fieldsets = (
        (
            "Identificación",
            {
                "fields": ("name", "slug", "category", "owner", "description"),
            },
        ),
        (
            "Contacto",
            {
                "fields": ("phone", "whatsapp", "email", "address"),
            },
        ),
        (
            "Ubicación",
            {
                "fields": ("latitude", "longitude"),
                "classes": ("collapse",),
            },
        ),
        (
            "Estado de verificación",
            {
                "fields": ("status", "rejection_reason"),
            },
        ),
        (
            "Auditoría",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "duration_minutes", "price", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "business__name")
    autocomplete_fields = ("business",)
    ordering = ("business", "name")

    @admin.action(description="Aprobar negocios seleccionados")
    def aprobar_negocios(self, request, queryset):
        actualizados = queryset.update(
            status=Business.Status.APPROVED, rejection_reason=""
        )
        self.message_user(request, f"{actualizados} negocio(s) aprobado(s).")

    @admin.action(description="Rechazar negocios seleccionados")
    def rechazar_negocios(self, request, queryset):
        actualizados = queryset.update(status=Business.Status.REJECTED)
        self.message_user(request, f"{actualizados} negocio(s) rechazado(s).")
