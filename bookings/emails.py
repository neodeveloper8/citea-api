from zoneinfo import ZoneInfo

from core.emails import enviar_email_seguro

_LIMA = ZoneInfo("America/Lima")


def _saludo(customer):
    return (customer.get_full_name() or "").strip() or "cliente"


def _fecha_local(dt):
    return dt.astimezone(_LIMA).strftime("%d/%m/%Y a las %H:%M")


def email_reserva_confirmada(booking):
    customer = booking.customer
    negocio = booking.business.name
    servicio = booking.service.name
    fecha = _fecha_local(booking.start_datetime)

    subject = f"Tu reserva en {negocio} fue confirmada — Citea"
    message = (
        f"Hola {_saludo(customer)},\n\n"
        f"Tu reserva en {negocio} fue confirmada.\n"
        f"Servicio: {servicio}\n"
        f"Fecha: {fecha}\n\n"
        f"¡Te esperamos!"
    )
    return enviar_email_seguro(subject=subject, message=message, to=customer.email)


def email_reserva_cancelada(booking):
    customer = booking.customer
    negocio = booking.business.name
    servicio = booking.service.name
    fecha = _fecha_local(booking.start_datetime)

    subject = f"Tu reserva en {negocio} fue cancelada — Citea"
    message = (
        f"Hola {_saludo(customer)},\n\n"
        f"Tu reserva en {negocio} fue cancelada.\n"
        f"Servicio: {servicio}\n"
        f"Fecha: {fecha}\n\n"
        f"Si no la cancelaste vos, contactá al negocio."
    )
    return enviar_email_seguro(subject=subject, message=message, to=customer.email)


def email_reserva_completada(booking):
    customer = booking.customer
    negocio = booking.business.name
    servicio = booking.service.name

    subject = f"Gracias por tu visita a {negocio} — Citea"
    message = (
        f"Hola {_saludo(customer)},\n\n"
        f"Gracias por tu visita a {negocio} para {servicio}.\n"
        f"¡Esperamos verte de nuevo pronto!"
    )
    return enviar_email_seguro(subject=subject, message=message, to=customer.email)
