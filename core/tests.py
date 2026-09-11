# Create your tests here.
from unittest.mock import patch

import pytest

from core.emails import enviar_email_seguro


@pytest.mark.django_db
def test_enviar_email_seguro_ok_con_locmem_devuelve_true(mailoutbox):
    resultado = enviar_email_seguro(
        subject="Asunto de prueba",
        message="Cuerpo de prueba",
        to="destino@test.pe",
    )

    assert resultado is True
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["destino@test.pe"]


@pytest.mark.django_db
def test_enviar_email_seguro_falla_no_propaga_y_devuelve_false(mailoutbox):
    with patch("core.emails.send_mail", side_effect=Exception("SMTP caído")):
        resultado = enviar_email_seguro(
            subject="Asunto de prueba",
            message="Cuerpo de prueba",
            to="destino@test.pe",
        )

    assert resultado is False
    assert len(mailoutbox) == 0
