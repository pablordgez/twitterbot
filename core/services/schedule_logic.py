"""
Schedule business logic service for T-011.

Handles schedule validation, timezone/DST computations,
content mode rules, version tracking, and next-occurrence calculation.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models.schedules import Schedule, ScheduleTargetAccount, ScheduleSourceList
from core.services.tweet_validation import validate_tweet_length


# ---------------------------------------------------------------------------
# Type helpers
# ---------------------------------------------------------------------------

def is_one_time(schedule: Schedule) -> bool:
    """Check if a schedule is one-time."""
    return schedule.schedule_type == Schedule.ScheduleType.ONE_TIME


def is_recurring(schedule: Schedule) -> bool:
    """Check if a schedule is recurring."""
    return schedule.schedule_type == Schedule.ScheduleType.RECURRING


# ---------------------------------------------------------------------------
# Timezone helpers
# ---------------------------------------------------------------------------

def validate_timezone(timezone_name: str) -> ZoneInfo:
    """
    Validate that *timezone_name* is a recognised IANA timezone.

    Returns the corresponding ``ZoneInfo`` on success.
    Raises ``ValidationError`` otherwise.
    """
    if not timezone_name:
        raise ValidationError("Timezone name is required.")
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, KeyError):
        raise ValidationError(f"Invalid timezone: {timezone_name}")


# ---------------------------------------------------------------------------
# Next-occurrence computation
# ---------------------------------------------------------------------------

def get_next_occurrence_time(
    schedule: Schedule,
    after: datetime | None = None,
) -> datetime | None:
    """
    Compute the next occurrence time for *schedule*.

    * **One-time** — returns ``start_datetime`` if it lies *after* the
      reference point (defaults to ``timezone.now()``).
    * **Recurring** — walks forward from ``start_datetime`` in increments
      of ``interval_value`` × ``interval_type`` using wall-clock arithmetic
      in the schedule's configured timezone so that DST transitions are
      handled transparently by ``zoneinfo``.

    Returns ``None`` when there is no future occurrence (one-time schedule
    whose time has already passed, or a cancelled schedule, etc.).
    """
    if schedule.status == 'canceled':
        return None

    if after is None:
        after = timezone.now()

    # Ensure *after* is offset-aware
    if after.tzinfo is None:
        after = after.replace(tzinfo=ZoneInfo("UTC"))

    tz = validate_timezone(schedule.timezone_name)

    if is_one_time(schedule):
        start = schedule.start_datetime
        if start.tzinfo is None:
            start = start.replace(tzinfo=tz)
        if start > after:
            return start
        return None

    # --- Recurring schedule ---
    if not schedule.interval_type or not schedule.interval_value:
        raise ValidationError(
            "Recurring schedules must have interval_type and interval_value."
        )

    start = schedule.start_datetime
    if start.tzinfo is None:
        start = start.replace(tzinfo=tz)

    # Convert to wall-clock time in the schedule's timezone so that
    # "every 24 hours" starting at 09:00 stays at 09:00 across DST.
    start_local = start.astimezone(tz)

    # Walk forward from start_local in wall-clock increments.
    candidate = start_local
    if schedule.interval_type == Schedule.IntervalType.HOURS:
        delta = timedelta(hours=schedule.interval_value)
    elif schedule.interval_type == Schedule.IntervalType.DAYS:
        delta = timedelta(days=schedule.interval_value)
    else:
        raise ValidationError(f"Unknown interval type: {schedule.interval_type}")

    # Fast-forward past *after* efficiently.
    if candidate <= after:
        # Calculate how many intervals we need to skip.
        diff = after - candidate
        total_seconds = delta.total_seconds()
        if total_seconds > 0:
            steps = int(diff.total_seconds() / total_seconds)
            candidate += delta * steps

        # Walk one step at a time from here to cross the threshold.
        while candidate <= after:
            candidate += delta

    return candidate


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_LIST_BASED_MODES = {
    Schedule.ContentMode.FIXED_FROM_LIST,
    Schedule.ContentMode.RANDOM_FROM_LIST,
    Schedule.ContentMode.RANDOM_FROM_LISTS,
}


def validate_schedule(
    schedule: Schedule,
    target_account_ids: list[int] | None = None,
    source_list_ids: list[int] | None = None,
) -> list[str]:
    """
    Validate a schedule's configuration.

    Returns a list of validation error messages.  An empty list means
    the schedule is valid.

    Parameters
    ----------
    schedule : Schedule
        The schedule instance to validate (need not be saved yet).
    target_account_ids : list[int] | None
        IDs of the target posting accounts.  If ``None``, the function
        queries the database for existing ``ScheduleTargetAccount`` rows.
    source_list_ids : list[int] | None
        IDs of the source tweet lists.  If ``None``, the function queries
        the database for existing ``ScheduleSourceList`` rows.
    """
    errors: list[str] = []

    # -- Timezone --
    try:
        validate_timezone(schedule.timezone_name)
    except ValidationError as exc:
        errors.append(str(exc.message))

    # -- Target accounts --
    if target_account_ids is not None:
        account_count = len(target_account_ids)
    elif schedule.pk:
        account_count = ScheduleTargetAccount.objects.filter(
            schedule=schedule,
        ).count()
    else:
        account_count = 0

    if account_count < 1:
        errors.append("At least one target account is required.")

    # -- Source lists --
    if source_list_ids is not None:
        list_count = len(source_list_ids)
    elif schedule.pk:
        list_count = ScheduleSourceList.objects.filter(
            schedule=schedule,
        ).count()
    else:
        list_count = 0

    # -- Content mode --
    mode = schedule.content_mode
    if mode == Schedule.ContentMode.FIXED_NEW:
        if not schedule.fixed_content:
            errors.append("Fixed content text is required for 'Fixed New' mode.")
        else:
            try:
                validate_tweet_length(schedule.fixed_content)
            except ValidationError as exc:
                errors.append(str(exc.message))
    elif mode == Schedule.ContentMode.FIXED_FROM_LIST:
        if list_count != 1:
            errors.append("Exactly one source list is required for 'Fixed From List' mode.")
    elif mode == Schedule.ContentMode.RANDOM_FROM_LIST:
        if list_count != 1:
            errors.append("Exactly one source list is required for 'Random From List' mode.")
    elif mode == Schedule.ContentMode.RANDOM_FROM_LISTS:
        if list_count < 1:
            errors.append("At least one source list is required for 'Random From Lists' mode.")

    # -- Recurring-only fields --
    if is_recurring(schedule):
        if not schedule.interval_type:
            errors.append("Interval type is required for recurring schedules.")
        if not schedule.interval_value or schedule.interval_value < 1:
            errors.append("Interval value must be a positive integer for recurring schedules.")
    else:
        # One-time schedules should not have reuse/exhaustion
        if schedule.reuse_enabled:
            errors.append("Reuse is not applicable to one-time schedules.")
        if schedule.exhaustion_behavior:
            errors.append("Exhaustion behavior is not applicable to one-time schedules.")

    # -- Reuse / exhaustion scoping --
    if is_recurring(schedule):
        if mode not in _LIST_BASED_MODES:
            if schedule.reuse_enabled:
                errors.append("Reuse is only applicable for list-based content modes.")
            if schedule.exhaustion_behavior:
                errors.append("Exhaustion behavior is only applicable for list-based content modes.")

    return errors


# ---------------------------------------------------------------------------
# Version tracking
# ---------------------------------------------------------------------------

def increment_version(schedule: Schedule) -> None:
    """Increment the schedule version counter and save."""
    schedule.version += 1
    schedule.save(update_fields=["version", "updated_at"])
