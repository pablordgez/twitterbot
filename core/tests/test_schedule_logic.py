"""
Tests for core.services.schedule_logic (T-011).
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from core.models.accounts import PostingAccount
from core.models.schedules import Schedule, ScheduleTargetAccount, ScheduleSourceList
from core.models.tweets import TweetList
from core.services.schedule_logic import (
    get_next_occurrence_time,
    increment_version,
    is_one_time,
    is_recurring,
    validate_schedule,
    validate_timezone,
)


class ScheduleHelperFactory:
    """Tiny helper to create common test fixtures."""

    @staticmethod
    def make_account(name: str = "TestAccount") -> PostingAccount:
        return PostingAccount.objects.create(name=name)

    @staticmethod
    def make_list(name: str = "TestList") -> TweetList:
        return TweetList.objects.create(name=name)

    @staticmethod
    def make_schedule(**overrides) -> Schedule:
        defaults = {
            "schedule_type": Schedule.ScheduleType.ONE_TIME,
            "timezone_name": "UTC",
            "start_datetime": timezone.now() + timedelta(hours=1),
            "content_mode": Schedule.ContentMode.FIXED_NEW,
            "fixed_content": "Hello world",
        }
        defaults.update(overrides)
        return Schedule.objects.create(**defaults)


# ===================================================================
# Type helpers
# ===================================================================


class TypeHelperTests(TestCase):
    def test_is_one_time(self):
        s = ScheduleHelperFactory.make_schedule()
        self.assertTrue(is_one_time(s))
        self.assertFalse(is_recurring(s))

    def test_is_recurring(self):
        s = ScheduleHelperFactory.make_schedule(
            schedule_type=Schedule.ScheduleType.RECURRING,
            interval_type=Schedule.IntervalType.HOURS,
            interval_value=2,
        )
        self.assertFalse(is_one_time(s))
        self.assertTrue(is_recurring(s))


# ===================================================================
# Timezone validation
# ===================================================================


class TimezoneValidationTests(TestCase):
    def test_valid_timezone(self):
        tz = validate_timezone("US/Eastern")
        self.assertIsInstance(tz, ZoneInfo)

    def test_utc_timezone(self):
        tz = validate_timezone("UTC")
        self.assertEqual(str(tz), "UTC")

    def test_invalid_timezone_raises(self):
        with self.assertRaises(ValidationError) as cm:
            validate_timezone("Not/A/Timezone")
        self.assertIn("Invalid timezone", str(cm.exception))

    def test_empty_timezone_raises(self):
        with self.assertRaises(ValidationError) as cm:
            validate_timezone("")
        self.assertIn("required", str(cm.exception))


# ===================================================================
# One-time next-occurrence
# ===================================================================


class OneTimeNextOccurrenceTests(TestCase):
    def test_future_start_returns_start(self):
        future = timezone.now() + timedelta(hours=2)
        s = ScheduleHelperFactory.make_schedule(start_datetime=future)
        result = get_next_occurrence_time(s)
        self.assertEqual(result, future)

    def test_past_start_returns_none(self):
        past = timezone.now() - timedelta(hours=2)
        s = ScheduleHelperFactory.make_schedule(start_datetime=past)
        result = get_next_occurrence_time(s)
        self.assertIsNone(result)

    def test_canceled_returns_none(self):
        future = timezone.now() + timedelta(hours=2)
        s = ScheduleHelperFactory.make_schedule(
            start_datetime=future, status="canceled",
        )
        result = get_next_occurrence_time(s)
        self.assertIsNone(result)

    def test_custom_after_parameter(self):
        start = datetime(2025, 6, 15, 12, 0, tzinfo=ZoneInfo("UTC"))
        s = ScheduleHelperFactory.make_schedule(start_datetime=start)

        # "after" before start → returns start
        before = datetime(2025, 6, 15, 10, 0, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(get_next_occurrence_time(s, after=before), start)

        # "after" after start → None
        later = datetime(2025, 6, 15, 14, 0, tzinfo=ZoneInfo("UTC"))
        self.assertIsNone(get_next_occurrence_time(s, after=later))


# ===================================================================
# Recurring next-occurrence
# ===================================================================


class RecurringNextOccurrenceTests(TestCase):
    def _make_recurring(self, **kw):
        defaults = {
            "schedule_type": Schedule.ScheduleType.RECURRING,
            "timezone_name": "UTC",
            "start_datetime": datetime(2025, 3, 1, 9, 0, tzinfo=ZoneInfo("UTC")),
            "content_mode": Schedule.ContentMode.FIXED_NEW,
            "fixed_content": "Recurring test",
            "interval_type": Schedule.IntervalType.HOURS,
            "interval_value": 6,
        }
        defaults.update(kw)
        return ScheduleHelperFactory.make_schedule(**defaults)

    def test_every_6_hours(self):
        s = self._make_recurring()
        after = datetime(2025, 3, 1, 10, 0, tzinfo=ZoneInfo("UTC"))
        result = get_next_occurrence_time(s, after=after)
        expected = datetime(2025, 3, 1, 15, 0, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(result, expected)

    def test_every_1_day(self):
        s = self._make_recurring(
            interval_type=Schedule.IntervalType.DAYS,
            interval_value=1,
        )
        after = datetime(2025, 3, 1, 12, 0, tzinfo=ZoneInfo("UTC"))
        result = get_next_occurrence_time(s, after=after)
        expected = datetime(2025, 3, 2, 9, 0, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(result, expected)

    def test_every_3_days(self):
        s = self._make_recurring(
            interval_type=Schedule.IntervalType.DAYS,
            interval_value=3,
        )
        after = datetime(2025, 3, 2, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = get_next_occurrence_time(s, after=after)
        expected = datetime(2025, 3, 4, 9, 0, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(result, expected)

    def test_start_in_future_returns_start(self):
        far_future = datetime(2099, 1, 1, 9, 0, tzinfo=ZoneInfo("UTC"))
        s = self._make_recurring(start_datetime=far_future)
        after = datetime(2025, 3, 1, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = get_next_occurrence_time(s, after=after)
        self.assertEqual(result, far_future)

    def test_missing_interval_raises(self):
        s = ScheduleHelperFactory.make_schedule(
            schedule_type=Schedule.ScheduleType.RECURRING,
            interval_type=None,
            interval_value=None,
        )
        with self.assertRaises(ValidationError):
            get_next_occurrence_time(s)


# ===================================================================
# DST handling
# ===================================================================


class DSTHandlingTests(TestCase):
    """
    US/Eastern springs forward on 2nd Sunday of March,
    falls back on 1st Sunday of November.
    2025 spring-forward: March 9 at 02:00 → 03:00.
    2025 fall-back:      November 2 at 02:00 → 01:00.
    """

    def test_spring_forward_daily(self):
        """Daily schedule at 09:00 Eastern should stay 09:00 after DST."""
        tz_name = "US/Eastern"
        tz = ZoneInfo(tz_name)
        # March 8, 2025 09:00 EST  →  March 9 DST springs forward
        start = datetime(2025, 3, 8, 9, 0, tzinfo=tz)
        s = ScheduleHelperFactory.make_schedule(
            schedule_type=Schedule.ScheduleType.RECURRING,
            timezone_name=tz_name,
            start_datetime=start,
            interval_type=Schedule.IntervalType.DAYS,
            interval_value=1,
        )
        # Ask for next occurrence after March 8 at 10:00
        after = datetime(2025, 3, 8, 10, 0, tzinfo=tz)
        result = get_next_occurrence_time(s, after=after)
        # Should be March 9, 09:00 EDT
        self.assertEqual(result.astimezone(tz).hour, 9)
        self.assertEqual(result.astimezone(tz).day, 9)

    def test_fall_back_daily(self):
        """Daily schedule at 09:00 Eastern should stay 09:00 after fall-back."""
        tz_name = "US/Eastern"
        tz = ZoneInfo(tz_name)
        # Nov 1, 2025 09:00 EDT  →  Nov 2 DST falls back
        start = datetime(2025, 11, 1, 9, 0, tzinfo=tz)
        s = ScheduleHelperFactory.make_schedule(
            schedule_type=Schedule.ScheduleType.RECURRING,
            timezone_name=tz_name,
            start_datetime=start,
            interval_type=Schedule.IntervalType.DAYS,
            interval_value=1,
        )
        after = datetime(2025, 11, 1, 10, 0, tzinfo=tz)
        result = get_next_occurrence_time(s, after=after)
        # Should be Nov 2, 09:00 EST
        self.assertEqual(result.astimezone(tz).hour, 9)
        self.assertEqual(result.astimezone(tz).day, 2)

    def test_spring_forward_hourly(self):
        """Hourly schedule should not skip or repeat around DST transition."""
        tz_name = "US/Eastern"
        tz = ZoneInfo(tz_name)
        # Every 2 hours starting at 00:00 on March 9 (spring-forward day)
        start = datetime(2025, 3, 9, 0, 0, tzinfo=tz)
        s = ScheduleHelperFactory.make_schedule(
            schedule_type=Schedule.ScheduleType.RECURRING,
            timezone_name=tz_name,
            start_datetime=start,
            interval_type=Schedule.IntervalType.HOURS,
            interval_value=2,
        )
        # After 00:00 → next should be 02:00 (which becomes 03:00 EDT)
        after = datetime(2025, 3, 9, 0, 30, tzinfo=tz)
        result = get_next_occurrence_time(s, after=after)
        # 2 hours after 00:00 = 02:00 EST → displayed as 03:00 EDT
        # The key thing is that a result is returned, not skipped
        self.assertIsNotNone(result)
        self.assertTrue(result > after)


# ===================================================================
# Content mode validation
# ===================================================================


class ContentModeValidationTests(TestCase):
    def test_fixed_new_valid(self):
        s = ScheduleHelperFactory.make_schedule(
            content_mode=Schedule.ContentMode.FIXED_NEW,
            fixed_content="Valid tweet",
        )
        acc = ScheduleHelperFactory.make_account()
        errors = validate_schedule(s, target_account_ids=[acc.pk])
        self.assertEqual(errors, [])

    def test_fixed_new_missing_content(self):
        s = ScheduleHelperFactory.make_schedule(
            content_mode=Schedule.ContentMode.FIXED_NEW,
            fixed_content="",
        )
        acc = ScheduleHelperFactory.make_account()
        errors = validate_schedule(s, target_account_ids=[acc.pk])
        self.assertTrue(any("Fixed content" in e for e in errors))

    def test_fixed_new_too_long(self):
        s = ScheduleHelperFactory.make_schedule(
            content_mode=Schedule.ContentMode.FIXED_NEW,
            fixed_content="A" * 300,
        )
        acc = ScheduleHelperFactory.make_account()
        errors = validate_schedule(s, target_account_ids=[acc.pk])
        self.assertTrue(any("too long" in e for e in errors))

    def test_fixed_from_list_requires_one_list(self):
        s = ScheduleHelperFactory.make_schedule(
            content_mode=Schedule.ContentMode.FIXED_FROM_LIST,
            fixed_content=None,
        )
        acc = ScheduleHelperFactory.make_account()
        # No lists
        errors = validate_schedule(s, target_account_ids=[acc.pk], source_list_ids=[])
        self.assertTrue(any("one source list" in e for e in errors))
        # One list ✓
        tl = ScheduleHelperFactory.make_list()
        errors = validate_schedule(s, target_account_ids=[acc.pk], source_list_ids=[tl.pk])
        self.assertEqual(errors, [])

    def test_random_from_list_requires_one_list(self):
        s = ScheduleHelperFactory.make_schedule(
            content_mode=Schedule.ContentMode.RANDOM_FROM_LIST,
            fixed_content=None,
        )
        acc = ScheduleHelperFactory.make_account()
        errors = validate_schedule(s, target_account_ids=[acc.pk], source_list_ids=[])
        self.assertTrue(any("one source list" in e for e in errors))

    def test_random_from_lists_requires_at_least_one(self):
        s = ScheduleHelperFactory.make_schedule(
            content_mode=Schedule.ContentMode.RANDOM_FROM_LISTS,
            fixed_content=None,
        )
        acc = ScheduleHelperFactory.make_account()
        # Zero lists
        errors = validate_schedule(s, target_account_ids=[acc.pk], source_list_ids=[])
        self.assertTrue(any("At least one source list" in e for e in errors))
        # Two lists ✓
        tl1 = ScheduleHelperFactory.make_list("L1")
        tl2 = ScheduleHelperFactory.make_list("L2")
        errors = validate_schedule(
            s, target_account_ids=[acc.pk], source_list_ids=[tl1.pk, tl2.pk],
        )
        self.assertEqual(errors, [])


# ===================================================================
# Multi-account validation
# ===================================================================


class MultiAccountValidationTests(TestCase):
    def test_no_accounts_rejected(self):
        s = ScheduleHelperFactory.make_schedule()
        errors = validate_schedule(s, target_account_ids=[])
        self.assertTrue(any("target account" in e for e in errors))

    def test_one_account_accepted(self):
        s = ScheduleHelperFactory.make_schedule()
        acc = ScheduleHelperFactory.make_account()
        errors = validate_schedule(s, target_account_ids=[acc.pk])
        self.assertEqual(errors, [])

    def test_multiple_accounts_accepted(self):
        s = ScheduleHelperFactory.make_schedule()
        a1 = ScheduleHelperFactory.make_account("A1")
        a2 = ScheduleHelperFactory.make_account("A2")
        errors = validate_schedule(s, target_account_ids=[a1.pk, a2.pk])
        self.assertEqual(errors, [])

    def test_db_lookup_when_ids_not_supplied(self):
        """When target_account_ids is None, validation queries the DB."""
        s = ScheduleHelperFactory.make_schedule()
        acc = ScheduleHelperFactory.make_account()
        ScheduleTargetAccount.objects.create(schedule=s, account=acc)
        errors = validate_schedule(s, target_account_ids=None)
        self.assertEqual(errors, [])


# ===================================================================
# Reuse / exhaustion validation
# ===================================================================


class ReuseExhaustionValidationTests(TestCase):
    def test_one_time_reuse_rejected(self):
        s = ScheduleHelperFactory.make_schedule(reuse_enabled=True)
        acc = ScheduleHelperFactory.make_account()
        errors = validate_schedule(s, target_account_ids=[acc.pk])
        self.assertTrue(any("Reuse" in e and "one-time" in e for e in errors))

    def test_one_time_exhaustion_rejected(self):
        s = ScheduleHelperFactory.make_schedule(
            exhaustion_behavior=Schedule.ExhaustionBehavior.STOP,
        )
        acc = ScheduleHelperFactory.make_account()
        errors = validate_schedule(s, target_account_ids=[acc.pk])
        self.assertTrue(any("Exhaustion" in e and "one-time" in e for e in errors))

    def test_recurring_fixed_new_reuse_rejected(self):
        s = ScheduleHelperFactory.make_schedule(
            schedule_type=Schedule.ScheduleType.RECURRING,
            content_mode=Schedule.ContentMode.FIXED_NEW,
            fixed_content="Hey",
            interval_type=Schedule.IntervalType.HOURS,
            interval_value=1,
            reuse_enabled=True,
        )
        acc = ScheduleHelperFactory.make_account()
        errors = validate_schedule(s, target_account_ids=[acc.pk])
        self.assertTrue(any("Reuse" in e and "list-based" in e for e in errors))

    def test_recurring_list_based_reuse_accepted(self):
        s = ScheduleHelperFactory.make_schedule(
            schedule_type=Schedule.ScheduleType.RECURRING,
            content_mode=Schedule.ContentMode.RANDOM_FROM_LIST,
            fixed_content=None,
            interval_type=Schedule.IntervalType.DAYS,
            interval_value=1,
            reuse_enabled=True,
        )
        acc = ScheduleHelperFactory.make_account()
        tl = ScheduleHelperFactory.make_list()
        errors = validate_schedule(
            s, target_account_ids=[acc.pk], source_list_ids=[tl.pk],
        )
        self.assertEqual(errors, [])

    def test_recurring_list_based_exhaustion_accepted(self):
        s = ScheduleHelperFactory.make_schedule(
            schedule_type=Schedule.ScheduleType.RECURRING,
            content_mode=Schedule.ContentMode.RANDOM_FROM_LIST,
            fixed_content=None,
            interval_type=Schedule.IntervalType.DAYS,
            interval_value=1,
            exhaustion_behavior=Schedule.ExhaustionBehavior.RESET,
        )
        acc = ScheduleHelperFactory.make_account()
        tl = ScheduleHelperFactory.make_list()
        errors = validate_schedule(
            s, target_account_ids=[acc.pk], source_list_ids=[tl.pk],
        )
        self.assertEqual(errors, [])


# ===================================================================
# Recurring field validation
# ===================================================================


class RecurringFieldValidationTests(TestCase):
    def test_missing_interval_type(self):
        s = ScheduleHelperFactory.make_schedule(
            schedule_type=Schedule.ScheduleType.RECURRING,
            interval_type=None,
            interval_value=None,
        )
        acc = ScheduleHelperFactory.make_account()
        errors = validate_schedule(s, target_account_ids=[acc.pk])
        self.assertTrue(any("Interval type" in e for e in errors))

    def test_zero_interval_value(self):
        s = ScheduleHelperFactory.make_schedule(
            schedule_type=Schedule.ScheduleType.RECURRING,
            interval_type=Schedule.IntervalType.HOURS,
            interval_value=0,
        )
        acc = ScheduleHelperFactory.make_account()
        errors = validate_schedule(s, target_account_ids=[acc.pk])
        self.assertTrue(any("positive integer" in e for e in errors))


# ===================================================================
# Invalid timezone in schedule
# ===================================================================


class InvalidTimezoneValidationTests(TestCase):
    def test_invalid_timezone(self):
        s = ScheduleHelperFactory.make_schedule(timezone_name="Fake/Zone")
        acc = ScheduleHelperFactory.make_account()
        errors = validate_schedule(s, target_account_ids=[acc.pk])
        self.assertTrue(any("Invalid timezone" in e for e in errors))


# ===================================================================
# Version tracking
# ===================================================================


class VersionTrackingTests(TestCase):
    def test_increment_version(self):
        s = ScheduleHelperFactory.make_schedule()
        self.assertEqual(s.version, 1)
        increment_version(s)
        s.refresh_from_db()
        self.assertEqual(s.version, 2)

    def test_multiple_increments(self):
        s = ScheduleHelperFactory.make_schedule()
        for expected in range(2, 6):
            increment_version(s)
            s.refresh_from_db()
            self.assertEqual(s.version, expected)
