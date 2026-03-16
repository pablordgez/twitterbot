"""
Dependency cascade service for T-018.

Centralises dependency checking (account / tweet-list → schedules) and
cascade cancellation (schedule + pending occurrences + audit trail).
"""
from django.db import transaction
from django.utils import timezone

from core.models.execution import Occurrence
from core.models.history import HistoryEvent
from core.models.schedules import Schedule, ScheduleSourceList, ScheduleTargetAccount


def check_account_dependencies(account):
    """Return active schedules that target *account*."""
    return list(
        Schedule.objects.filter(
            status='active',
            target_accounts__account=account,
        ).distinct()
    )


def check_list_dependencies(tweet_list):
    """Return active schedules that source *tweet_list*."""
    return list(
        Schedule.objects.filter(
            status='active',
            source_lists__tweet_list=tweet_list,
        ).distinct()
    )


def cascade_cancel(schedules, reason):
    """Cancel each schedule and its pending occurrences, logging audit events.

    Parameters
    ----------
    schedules : iterable[Schedule]
        Schedules to cancel.
    reason : str
        Value stored in ``Occurrence.cancel_reason`` and in the audit
        event detail (e.g. ``'account_deleted'``, ``'list_deleted'``).
    """
    now = timezone.now()
    with transaction.atomic():
        for schedule in schedules:
            # 1. Mark schedule canceled
            schedule.status = 'canceled'
            schedule.save(update_fields=['status', 'updated_at'])

            # 2. Bulk-cancel pending occurrences
            schedule.occurrences.filter(
                status=Occurrence.Status.PENDING,
            ).update(
                status=Occurrence.Status.CANCELED,
                cancel_reason=reason,
                updated_at=now,
            )

            # 3. Audit event per schedule
            HistoryEvent.objects.create(
                event_type='DEPENDENCY_CASCADE_CANCEL',
                schedule=schedule,
                detail={'reason': reason},
            )
