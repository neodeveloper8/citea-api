import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def enviar_email_seguro(*, subject, message, to, from_email=None):
    """Envía un email y NUNCA propaga el fallo: loguea con traceback y
    devuelve False. Para side-effects post-commit donde un mail caído no
    debe voltear ni ensuciar la operación principal. El except amplio es
    el contrato deliberado, no un descuido."""
    from_email = from_email or settings.DEFAULT_FROM_EMAIL
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[to],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Fallo al enviar email a %s (subject=%r)", to, subject)
        return False
