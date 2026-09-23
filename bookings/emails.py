from zoneinfo import ZoneInfo

from core.emails import enviar_email_seguro

_LIMA = ZoneInfo("America/Lima")


def _nombre_cliente(booking):
    """Nombre a mostrar: el del customer si hay cuenta, si no el guest_name
    (booking direct telefónico)."""
    if booking.customer is not None:
        return booking.customer.get_full_name()
    return booking.guest_name


def _saludo(booking):
    return (_nombre_cliente(booking) or "").strip() or "cliente"


def _fecha_local(dt):
    return dt.astimezone(_LIMA).strftime("%d/%m/%Y a las %H:%M")


def email_reserva_confirmada(booking):
    # Un booking direct (guest, sin cuenta) no tiene email al cual mandar.
    # Nunca manda mail: decisión deliberada, no un descuido.
    if booking.customer is None:
        return False

    negocio = booking.business.name
    servicio = booking.service.name
    fecha = _fecha_local(booking.start_datetime)

    subject = f"Tu reserva en {negocio} fue confirmada — Citea"
    message = (
        f"Hola {_saludo(booking)},\n\n"
        f"Tu reserva en {negocio} fue confirmada.\n"
        f"Servicio: {servicio}\n"
        f"Fecha: {fecha}\n\n"
        f"¡Te esperamos!"
    )
    return enviar_email_seguro(
        subject=subject, message=message, to=booking.customer.email
    )


def email_reserva_cancelada(booking):
    if booking.customer is None:
        return False

    negocio = booking.business.name
    servicio = booking.service.name
    fecha = _fecha_local(booking.start_datetime)

    subject = f"Tu reserva en {negocio} fue cancelada — Citea"
    message = (
        f"Hola {_saludo(booking)},\n\n"
        f"Tu reserva en {negocio} fue cancelada.\n"
        f"Servicio: {servicio}\n"
        f"Fecha: {fecha}\n\n"
        f"Si no la cancelaste vos, contactá al negocio."
    )
    return enviar_email_seguro(
        subject=subject, message=message, to=booking.customer.email
    )


def email_reserva_completada(booking):
    if booking.customer is None:
        return False

    negocio = booking.business.name
    servicio = booking.service.name

    subject = f"Gracias por tu visita a {negocio} — Citea"
    message = (
        f"Hola {_saludo(booking)},\n\n"
        f"Gracias por tu visita a {negocio} para {servicio}.\n"
        f"¡Esperamos verte de nuevo pronto!"
    )
    return enviar_email_seguro(
        subject=subject, message=message, to=booking.customer.email
    )


def email_recordatorio(booking):
    if booking.customer is None:
        return False

    cuando = _fecha_local(booking.start_datetime)
    negocio = booking.business.name

    return enviar_email_seguro(
        subject=f"Recordatorio: tu reserva en {negocio} es mañana — Citea",
        message=(
            f"Hola {_saludo(booking)},\n\n"
            f"Te recordamos tu reserva en {negocio} para {cuando}.\n"
            f"Servicio: {booking.service.name}.\n\n"
            f"Si no vas a poder asistir, cancelá con tiempo. ¡Te esperamos!"
        ),
        to=booking.customer.email,
    )
