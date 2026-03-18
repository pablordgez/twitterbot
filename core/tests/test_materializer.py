from django.test import TestCase
import zoneinfo
from datetime import timedelta
from django.utils import timezone
from core.models.schedules import Schedule
from core.models.execution import Occurrence
from core.services.occurrence_materializer import materialize_for_schedule, refresh_rolling_horizon

class MaterializerTests(TestCase):

    def test_one_time_materialization(self):
        now = timezone.now()
        future_start = now + timedelta(days=1)

        schedule = Schedule.objects.create(
            schedule_type=Schedule.ScheduleType.ONE_TIME,
            timezone_name="UTC",
            start_datetime=future_start,
            content_mode=Schedule.ContentMode.FIXED_NEW,
            status='active',
            version=1
        )

        # Materialize
        materialize_for_schedule(schedule)

        occurrences = Occurrence.objects.filter(schedule=schedule)
        self.assertEqual(occurrences.count(), 1)
        self.assertEqual(occurrences.first().due_at, future_start)
        self.assertEqual(occurrences.first().display_timezone, "UTC")
        self.assertEqual(occurrences.first().schedule_version, 1)
        self.assertEqual(occurrences.first().status, Occurrence.Status.PENDING)

        # Running again shouldn't duplicate
        materialize_for_schedule(schedule)
        self.assertEqual(Occurrence.objects.filter(schedule=schedule).count(), 1)

    def test_recurring_hours_materialization(self):
        now = timezone.now()
        start_dt = now + timedelta(hours=1)

        schedule = Schedule.objects.create(
            schedule_type=Schedule.ScheduleType.RECURRING,
            timezone_name="UTC",
            start_datetime=start_dt,
            interval_type=Schedule.IntervalType.HOURS,
            interval_value=2,
            content_mode=Schedule.ContentMode.FIXED_NEW,
            status='active',
            version=1
        )

        materialize_for_schedule(schedule)

        # 30 days = 720 hours. Given interval 2 hours => ~360 occurrences
        occurrences = Occurrence.objects.filter(schedule=schedule).order_by('due_at')
        self.assertTrue(occurrences.count() > 300)
        self.assertTrue(occurrences.count() <= 360)

        first = occurrences.first()
        second = occurrences[1]

        self.assertEqual(first.due_at, start_dt)
        self.assertEqual(second.due_at, start_dt + timedelta(hours=2))

    def test_dst_boundary_preservation(self):
        tz = zoneinfo.ZoneInfo("US/Eastern")
        naive_start = timezone.datetime(2026, 3, 7, 10, 0, 0)
        start_dt = timezone.make_aware(naive_start, timezone=tz)

        # Django's TestCase doesn't have an easy timezone.now mocker,
        # but since start_dt is fixed to 2026, we just let it create occurrences.
        # BUT materialize_for_schedule skips past occurrences if start is in the past!
        # Oh right! "now = timezone.now()". So we need to mock it if we use 2026.
        # Alternatively, we just pick NEXT year's DST transition!
        # E.g. March 14, 2027
        # Let's find the US/Eastern DST offset for the current year or next.

        # Just mock timezone.now using unittest.mock
        from unittest.mock import patch

        mock_now = timezone.make_aware(timezone.datetime(2026, 3, 1, 0, 0, 0), timezone=tz)

        with patch('core.services.occurrence_materializer.timezone.now', return_value=mock_now):
            schedule = Schedule.objects.create(
                schedule_type=Schedule.ScheduleType.RECURRING,
                timezone_name="US/Eastern",
                start_datetime=start_dt,
                interval_type=Schedule.IntervalType.DAYS,
                interval_value=1,
                content_mode=Schedule.ContentMode.FIXED_NEW,
                status='active',
                version=1
            )

            materialize_for_schedule(schedule)

            occurrences = Occurrence.objects.filter(schedule=schedule).order_by('due_at')
            self.assertTrue(occurrences.count() > 0)

            occ_7th = occurrences[0]
            self.assertEqual(occ_7th.due_at.astimezone(tz).hour, 10)
            self.assertEqual(occ_7th.due_at.astimezone(tz).day, 7)

            occ_8th = occurrences[1]
            self.assertEqual(occ_8th.due_at.astimezone(tz).hour, 10)
            self.assertEqual(occ_8th.due_at.astimezone(tz).day, 8)

            occ_9th = occurrences[2]
            self.assertEqual(occ_9th.due_at.astimezone(tz).hour, 10)
            self.assertEqual(occ_9th.due_at.astimezone(tz).day, 9)

            delta = occ_8th.due_at - occ_7th.due_at
            self.assertEqual(delta, timedelta(hours=23))

            delta2 = occ_9th.due_at - occ_8th.due_at
            self.assertEqual(delta2, timedelta(hours=24))

    def test_edit_immutability(self):
        now = timezone.now()
        start_dt = now - timedelta(days=2) # Started two days ago

        schedule = Schedule.objects.create(
            schedule_type=Schedule.ScheduleType.RECURRING,
            timezone_name="UTC",
            start_datetime=start_dt,
            interval_type=Schedule.IntervalType.DAYS,
            interval_value=1,
            content_mode=Schedule.ContentMode.FIXED_NEW,
            status='active',
            version=1
        )

        # Manually create some past occurrences that should NOT be touched
        past_occ = Occurrence.objects.create(
            schedule=schedule,
            due_at=now - timedelta(days=1),
            display_timezone="UTC",
            schedule_version=1,
            status=Occurrence.Status.COMPLETED
        )

        pending_past_occ = Occurrence.objects.create(
            schedule=schedule,
            due_at=now - timedelta(hours=1),
            display_timezone="UTC",
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )

        # Run materializer
        materialize_for_schedule(schedule)

        past_occ.refresh_from_db()
        pending_past_occ.refresh_from_db()

        # Should still exist
        self.assertTrue(Occurrence.objects.filter(id=past_occ.id).exists())
        self.assertTrue(Occurrence.objects.filter(id=pending_past_occ.id).exists())

        # Simulate an edit
        schedule.version = 2
        schedule.interval_value = 2 # Change interval
        schedule.save()

        materialize_for_schedule(schedule)

        # Past ones must still be untouched
        self.assertTrue(Occurrence.objects.filter(id=past_occ.id).exists())
        self.assertTrue(Occurrence.objects.filter(id=pending_past_occ.id).exists())

        # New future occurrences should have version 2
        new_occs = Occurrence.objects.filter(schedule=schedule, due_at__gt=now).order_by('due_at')
        self.assertTrue(new_occs.count() > 0)
        for occ in new_occs:
            self.assertEqual(occ.schedule_version, 2)
            self.assertEqual(occ.status, Occurrence.Status.PENDING)

    def test_refresh_rolling_horizon(self):
        now = timezone.now()
        start_dt = now + timedelta(days=1)

        schedule = Schedule.objects.create(
            schedule_type=Schedule.ScheduleType.RECURRING,
            timezone_name="UTC",
            start_datetime=start_dt,
            interval_type=Schedule.IntervalType.DAYS,
            interval_value=1,
            content_mode=Schedule.ContentMode.FIXED_NEW,
            status='active',
            version=1
        )

        refresh_rolling_horizon()

        # Should have generated up to 30 days
        self.assertEqual(Occurrence.objects.filter(schedule=schedule).count(), 30)
