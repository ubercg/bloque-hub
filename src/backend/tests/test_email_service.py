"""Unit tests for the SMTP email backend (PR#9 FIX 4, CRITICAL).

`smtplib.SMTP(...)` had no explicit socket timeout — a hung/black-holed SMTP
connection could block the worker thread indefinitely. Assert a bounded
`timeout` is always passed.
"""

from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.modules.notifications import email_service


class TestSmtpTimeout:
    def test_send_smtp_passes_bounded_timeout(self, monkeypatch):
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp")
        monkeypatch.setattr(settings, "SMTP_USER", "")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "")

        mock_smtp_instance = MagicMock()
        mock_smtp_instance.__enter__.return_value = mock_smtp_instance
        mock_smtp_instance.__exit__.return_value = False

        with patch("smtplib.SMTP", return_value=mock_smtp_instance) as mock_smtp_cls:
            email_service.send_email(
                to="destinatario@example.com",
                subject="Asunto de prueba",
                html_body="<p>hola</p>",
            )

        assert mock_smtp_cls.call_count == 1
        _, kwargs = mock_smtp_cls.call_args
        assert "timeout" in kwargs
        assert isinstance(kwargs["timeout"], (int, float))
        assert 0 < kwargs["timeout"] <= 60

    def test_smtp_timeout_setting_defaults_to_a_bounded_value(self):
        assert 0 < settings.SMTP_TIMEOUT_SECONDS <= 60
