from django.dispatch import receiver
from axes.signals import user_locked_out

from core.services.history import log_event


@receiver(user_locked_out)
def log_lockout_threshold(sender, request, username=None, ip_address=None, **kwargs):
    log_event(
        'AUTH_LOCKOUT_THRESHOLD',
        detail={
            'username': username or '',
            'ip_address': ip_address or '',
        },
    )
