from datetime import timedelta

from django.utils import timezone

from bookings.emails import email_recordatorio
from bookings.models import Booking


def enviar_recordatorios(ahora):
    """Barre las reservas CONFIRMED que empiezan en la franja [ahora+23h,
    ahora+24h), aún no recordadas, con cliente con cuenta (los guests no
    tienen email). Manda el recordatorio y marca reminder_sent_at para no
    repetir. Idempotente: correr dos veces no re-manda (el filtro isnull lo
    evita). Reloj inyectado -> testeable sin esperar 24h reales.
    Devuelve la cantidad de recordatorios procesados."""
    desde = ahora + timedelta(hours=23)
    hasta = ahora + timedelta(hours=24)
    pendientes = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        start_datetime__gte=desde,
        start_datetime__lt=hasta,
        reminder_sent_at__isnull=True,
        customer__isnull=False,
    ).select_related("customer", "business", "service")

    procesados = 0
    for booking in pendientes:
        email_recordatorio(booking)  # best-effort (no propaga)
        booking.reminder_sent_at = ahora  # marco pase lo que pase
        booking.save(update_fields=["reminder_sent_at", "updated_at"])
        procesados += 1
    return procesados


def task_enviar_recordatorios():
    """Wrapper para django-q2: inyecta el reloj real. La lógica vive en
    enviar_recordatorios (función pura, testeable)."""
    return enviar_recordatorios(timezone.now())
