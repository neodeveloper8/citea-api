from datetime import timedelta

from django.conf import settings

from bookings.models import Booking


def contar_noshows_recientes(*, customer, business, ahora):
    """Cuenta los no-shows de este cliente EN ESTE negocio dentro de la
    ventana móvil (settings.CITEA_NOSHOW_VENTANA_DIAS), medidos por la fecha
    del turno (start_datetime), no por created_at. Función pura: 'ahora' se
    inyecta para que los tests controlen el reloj."""
    desde = ahora - timedelta(days=settings.CITEA_NOSHOW_VENTANA_DIAS)
    return Booking.objects.filter(
        customer=customer,
        business=business,
        status=Booking.Status.NO_SHOW,
        start_datetime__gte=desde,
    ).count()


def esta_restringido(*, customer, business, ahora):
    """True si el cliente alcanzó el umbral de no-shows en la ventana."""
    return (
        contar_noshows_recientes(customer=customer, business=business, ahora=ahora)
        >= settings.CITEA_NOSHOW_UMBRAL
    )
