import csv
import io

from django.db.models import Count, Max

from bookings.models import Booking

COLUMNAS = [
    "nombre",
    "email",
    "telefono",
    "visitas",
    "ultima_visita",
    "servicio_mas_frecuente",
]


def recolectar_clientes(business):
    """Devuelve una lista de dicts, uno por CLIENTE ÚNICO con >=1 booking
    COMPLETED en el negocio. Dos queries agrupadas (no N+1):
    1) agregados por cliente (visitas, última visita)
    2) servicio más frecuente por cliente (modo), resuelto en un dict."""
    completed = Booking.objects.filter(
        business=business, status=Booking.Status.COMPLETED
    )

    # Query 1: agregados por cliente
    agregados = (
        completed.values("customer")
        .annotate(visitas=Count("id"), ultima=Max("start_datetime"))
        .order_by("-visitas")
    )

    # Query 2: servicio más frecuente por cliente (modo)
    # (customer, service) -> conteo; nos quedamos con el top por customer
    por_servicio = (
        completed.values("customer", "service__name")
        .annotate(n=Count("id"))
        .order_by("customer", "-n", "service__name")
    )
    servicio_top = {}
    for fila in por_servicio:
        cid = fila["customer"]
        if cid not in servicio_top:  # el primero por customer es el de mayor n
            servicio_top[cid] = fila["service__name"]

    # Traer datos de contacto de los clientes en UNA query
    from django.contrib.auth import get_user_model

    User = get_user_model()
    ids = [a["customer"] for a in agregados]
    users = {u.id: u for u in User.objects.filter(id__in=ids)}

    filas = []
    for a in agregados:
        u = users.get(a["customer"])
        if u is None:
            continue
        filas.append(
            {
                "nombre": u.get_full_name(),
                "email": u.email,
                "telefono": u.phone,
                "visitas": a["visitas"],
                "ultima_visita": a["ultima"].date().isoformat() if a["ultima"] else "",
                "servicio_mas_frecuente": servicio_top.get(a["customer"], ""),
            }
        )
    return filas


def generar_csv(filas):
    """Función pura: recibe la lista de dicts y devuelve el CSV como string.
    Testeable sin HTTP."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNAS)
    writer.writeheader()
    writer.writerows(filas)
    return buffer.getvalue()
