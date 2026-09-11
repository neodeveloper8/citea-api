# bookings/exceptions.py
class TransicionInvalida(Exception):
    """El Booking no puede pasar de `estado_actual` con la acción `accion`."""

    def __init__(self, *, estado_actual, accion, permitidos):
        self.estado_actual = estado_actual
        self.accion = accion
        self.permitidos = permitidos
        super().__init__(
            f"No se puede '{accion}' un booking en estado '{estado_actual}' "
            f"(orígenes válidos: {sorted(permitidos)})."
        )
