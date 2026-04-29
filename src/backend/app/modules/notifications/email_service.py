"""Servicio de envío de correo: interfaz con implementación mock y SMTP."""

from pathlib import Path

from app.core.config import settings


def send_email(
    to: str | list[str],
    subject: str,
    html_body: str,
    text_body: str | None = None,
    attachments: list[tuple[str, bytes]] | None = None,
) -> None:
    """
    Envía un correo. Si EMAIL_PROVIDER=mock, escribe en data/emails/ o log.
    Si smtp, usa SMTP configurado. attachments: list of (filename, bytes).
    """
    to_list = [to] if isinstance(to, str) else to
    if settings.EMAIL_PROVIDER.lower() == "mock":
        _send_mock(to_list, subject, html_body, text_body, attachments)
    else:
        _send_smtp(to_list, subject, html_body, text_body, attachments)


def _send_mock(
    to_list: list[str],
    subject: str,
    html_body: str,
    text_body: str | None,
    attachments: list[tuple[str, bytes]] | None,
) -> None:
    base = Path("data/emails")
    base.mkdir(parents=True, exist_ok=True)
    import time
    prefix = f"{int(time.time() * 1000)}"
    for i, addr in enumerate(to_list):
        safe = addr.replace("@", "_at_")
        path = base / f"{prefix}_{i}_{safe}.html"
        path.write_text(f"To: {addr}\nSubject: {subject}\n\n{html_body}", encoding="utf-8")
    if attachments:
        for name, data in attachments:
            (base / f"{prefix}_att_{name}").write_bytes(data)


def _send_smtp(
    to_list: list[str],
    subject: str,
    html_body: str,
    text_body: str | None,
    attachments: list[tuple[str, bytes]] | None,
) -> None:
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = ", ".join(to_list)
    plain = text_body if text_body else (html_body.replace("<br>", "\n").replace("</p>", "\n") if html_body else "")
    msg.attach(MIMEText(plain, "plain"))
    if html_body:
        msg.attach(MIMEText(html_body, "html"))
    if attachments:
        for filename, data in attachments:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(data)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={filename}")
            msg.attach(part)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            smtp.starttls()
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.sendmail(settings.SMTP_FROM, to_list, msg.as_string())
