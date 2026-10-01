"""Sending documents to clients by email, with a PDF attachment and an audit trail."""
import logging

from django.conf import settings
from django.core.mail import EmailMessage

from .models import AuditLog, FirmSettings

log = logging.getLogger(__name__)


class EmailFailed(Exception):
    pass


def send_document(*, user, to, subject, body, filename, pdf_bytes, obj, cc_sender=True):
    firm = FirmSettings.load()
    reply_to = [firm.email] if firm.email else []
    cc = [user.email] if cc_sender and user.email else []
    message = EmailMessage(subject=subject, body=body, from_email=settings.DEFAULT_FROM_EMAIL, to=[to], cc=cc,
                           reply_to=reply_to)
    message.attach(filename, pdf_bytes, "application/pdf")
    try:
        message.send(fail_silently=False)
    except Exception as exc:  # noqa: BLE001 - SMTP errors come in many shapes
        log.exception("Email to %s failed", to)
        raise EmailFailed(str(exc)) from exc
    AuditLog.record(user, "email", obj, f"Emailed {filename} to {to}")
