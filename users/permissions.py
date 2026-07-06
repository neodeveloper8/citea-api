from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsCliente(BasePermission):
    """Solo usuarios con rol 'cliente'. Ej: crear una reserva."""

    message = "Esta acción es solo para clientes."

    def has_permission(self, request, view):
        # request.user.is_authenticated primero: si es anónimo, no tiene .role.
        # El 'and' corta antes de evaluar is_cliente si no está logueado (evita error).
        return bool(
            request.user and request.user.is_authenticated and request.user.is_cliente
        )


class IsDueno(BasePermission):
    """Solo usuarios con rol 'dueno'. Ej: crear/gestionar un negocio."""

    message = "Esta acción es solo para dueños de negocio."

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and request.user.is_dueno
        )


class IsPlatformAdmin(BasePermission):
    """Solo administradores de plataforma (nosotros). Ej: aprobar negocios."""

    message = "Esta acción es solo para administradores de la plataforma."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_platform_admin
        )


class IsOwnerOrReadOnly(BasePermission):
    """
    Lectura libre; escritura solo para el dueño del objeto.
    La ruta al dueño se declara en la view con `owner_field`.
    Por defecto 'owner' (caso Business).
    """

    message = "Solo puedes modificar tus propios recursos."

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True

        owner_field = getattr(view, "owner_field", "owner")
        owner = obj
        for part in owner_field.split("."):
            owner = getattr(owner, part)
        return owner == request.user
