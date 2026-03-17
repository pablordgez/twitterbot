import logging
from django.core.mail import get_connection, EmailMessage
from django.utils import timezone

from core.models.accounts import PostingAccount
from core.models.notifications import SMTPSettings, NotificationRecipient, NotificationAccountState
from core.models.history import HistoryEvent
from core.models.execution import OccurrenceAttempt
from core.services.encryption import decrypt

logger = logging.getLogger(__name__)

def handle_posting_result(account: PostingAccount, success: bool, attempt: OccurrenceAttempt = None):
    """
    Evaluates notification rules and sends email if necessary.
    Should be called after a posting attempt finishes.
    """
    if success:
        _handle_success(account)
    else:
        _handle_failure(account, attempt)

def _handle_success(account: PostingAccount):
    state, _ = NotificationAccountState.objects.get_or_create(account=account)
    state.last_success_at = timezone.now()
    if state.first_failure_notified:
        state.first_failure_notified = False
    state.save(update_fields=['last_success_at', 'first_failure_notified', 'updated_at'])

def _handle_failure(account: PostingAccount, attempt: OccurrenceAttempt):
    mode = account.notification_mode
    if mode == PostingAccount.NotificationMode.NONE:
        return

    state, _ = NotificationAccountState.objects.get_or_create(account=account)
    
    should_send = False
    if mode == PostingAccount.NotificationMode.EVERY_FAILURE:
        should_send = True
    elif mode == PostingAccount.NotificationMode.FIRST_FAILURE:
        if not state.first_failure_notified:
            should_send = True

    if should_send:
        sent = _send_failure_email(account, attempt)
        if sent and mode == PostingAccount.NotificationMode.FIRST_FAILURE:
            state.first_failure_notified = True
            state.save(update_fields=['first_failure_notified', 'updated_at'])

def _send_failure_email(account: PostingAccount, attempt: OccurrenceAttempt) -> bool:
    try:
        settings = SMTPSettings.objects.first()
        if not settings or not settings.host:
            logger.warning("SMTP settings not configured. Skipping notification.")
            return False

        recipients = list(NotificationRecipient.objects.values_list('email', flat=True))
        if not recipients:
            logger.warning("No notification recipients configured. Skipping notification.")
            return False

        password = ""
        if settings.encrypted_password:
            decrypted = decrypt(settings.encrypted_password)
            password = decrypted.decode('utf-8') if isinstance(decrypted, bytes) else decrypted

        # Map SMTPSettings to Django connection kwargs
        # Django: use_ssl for Implicit TLS, use_tls for STARTTLS
        # SMTPSettings: use_tls for Implicit TLS, use_starttls for STARTTLS
        connection = get_connection(
            host=settings.host,
            port=settings.port,
            username=settings.username,
            password=password,
            use_tls=settings.use_starttls,
            use_ssl=settings.use_tls,
            fail_silently=False,
        )

        schedule_ref = "Unknown Schedule"
        if attempt and attempt.occurrence and attempt.occurrence.schedule:
            schedule_ref = f"Schedule #{attempt.occurrence.schedule.id}"

        time_str = timezone.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        error_detail = attempt.error_detail if attempt else "Unknown error"

        subject = f"[TwitterBot] Posting Failure: {account.name}"
        body = (
            f"A scheduled post failed.\n\n"
            f"Account: {account.name}\n"
            f"Schedule: {schedule_ref}\n"
            f"Time: {time_str}\n"
            f"Error Summary: {error_detail}\n\n"
            f"Please check the system history for more details."
        )

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.sender_email,
            to=recipients,
            connection=connection
        )
        email.send()
        
        # Log successful notification sending
        HistoryEvent.objects.create(
            event_type='NOTIFICATION_SENT',
            account=account,
            occurrence=attempt.occurrence if attempt else None,
            content_summary=f"Failure notification sent for {account.name}"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to send notification email: {e}")
        HistoryEvent.objects.create(
            event_type='NOTIFICATION_FAILED',
            account=account,
            occurrence=attempt.occurrence if attempt else None,
            content_summary=f"Notification delivery failed: {str(e)}"
        )
        return False
