import zoneinfo
from datetime import timedelta
from django.utils import timezone
from core.models.schedules import Schedule
from core.models.execution import Occurrence

def materialize_for_schedule(schedule: Schedule) -> None:
    """
    Generates and persists upcoming occurrences for a given schedule.
    - One-time: exactly 1 occurrence at start_datetime.
    - Recurring: generates up to 30 days of future occurrences from now.
    - Edits (or re-runs): Deletes strictly future pending occurrences and regenerates them.
    - Past/completed/failed/missed occurrences remain immutable.
    """
    now = timezone.now()

    # Delete pending occurrences strictly in the future.
    # We do NOT touch past occurrences or currently running ones.
    Occurrence.objects.filter(
        schedule=schedule,
        status=Occurrence.Status.PENDING,
        due_at__gt=now
    ).delete()

    if schedule.status == 'canceled':
        return

    expected_version = schedule.version

    if schedule.schedule_type == Schedule.ScheduleType.ONE_TIME:
        # Generate 1 occurrence if it's strictly in the future
        # (If it's in the past and pending, it wasn't deleted and is already there. If it wasn't created yet, we create it)
        # Spec says: one-time -> create 1 occurrence.
        # Let's check if there are ANY occurrences for this one-time schedule.
        # If there are none, we create it.
        if not Occurrence.objects.filter(schedule=schedule).exists():
            Occurrence.objects.create(
                schedule=schedule,
                due_at=schedule.start_datetime,
                display_timezone=schedule.timezone_name,
                schedule_version=expected_version,
                status=Occurrence.Status.PENDING
            )
        return

    if schedule.schedule_type == Schedule.ScheduleType.RECURRING:
        if not schedule.interval_type or not schedule.interval_value:
            return

        horizon = now + timedelta(days=30)

        # Determine the maximum due_at of occurrences that were NOT deleted.
        # This prevents us from generating overlapping occurrences.
        last_occurrence = Occurrence.objects.filter(schedule=schedule).order_by('-due_at').first()
        resume_after = last_occurrence.due_at if last_occurrence else None

        current_dt = schedule.start_datetime

        # Hop from start_datetime to horizon
        # Safety limit to prevent infinite loops (e.g., interval is 0)
        max_iterations = 10000
        iterations = 0

        while current_dt <= horizon and iterations < max_iterations:
            iterations += 1

            # We only create the occurrence if it's strictly in the future (due_at > now)
            # AND it's strictly after the last existing occurrence we kept (resume_after)
            if current_dt > now and (not resume_after or current_dt > resume_after):
                Occurrence.objects.create(
                    schedule=schedule,
                    due_at=current_dt,
                    display_timezone=schedule.timezone_name,
                    schedule_version=expected_version,
                    status=Occurrence.Status.PENDING
                )

            # Hop to the next interval
            current_dt = _calc_next_due_at(current_dt, schedule)

        return

def refresh_rolling_horizon() -> None:
    """
    Called periodically by the scheduler loop to extend the 30-day window
    for all active recurring schedules.
    """
    from django.db import transaction

    active_recurring_schedules = Schedule.objects.filter(
        status='active',
        schedule_type=Schedule.ScheduleType.RECURRING
    )

    for schedule in active_recurring_schedules:
        # Wrap each materialization in its own transaction to prevent one failure from stopping all
        try:
            with transaction.atomic():
                materialize_for_schedule(schedule)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to refresh rolling horizon for schedule {schedule.id}: {e}")

def _calc_next_due_at(base_dt, schedule: Schedule):
    """
    Calculates the next due_at time for a recurring schedule.
    Safely handles timezone and DST boundaries.
    """
    if schedule.interval_type == Schedule.IntervalType.HOURS:
        return base_dt + timedelta(hours=schedule.interval_value)

    elif schedule.interval_type == Schedule.IntervalType.DAYS:
        try:
            tz = zoneinfo.ZoneInfo(schedule.timezone_name)
        except Exception:
            # Fallback to UTC if timezone is invalid
            tz = zoneinfo.ZoneInfo("UTC")

        # 1. Convert to the schedule's display timezone
        local_base = base_dt.astimezone(tz)

        # 2. Get the naive representation in that timezone
        naive_base = local_base.replace(tzinfo=None)

        # 3. Add calendar days
        naive_next = naive_base + timedelta(days=schedule.interval_value)

        # 4. Make aware again in the same timezone
        next_dt = timezone.make_aware(naive_next, timezone=tz)
        return next_dt

    # Fallback to just returning base + interval to avoid infinite loop
    return base_dt + timedelta(hours=24)
