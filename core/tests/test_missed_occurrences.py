from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from core.models.schedules import Schedule, ScheduleTargetAccount
from core.models.accounts import PostingAccount
from core.models.execution import Occurrence
from core.models.history import HistoryEvent
from core.services.scheduler import startup_scan_missed, execute_scheduler_tick
from core.services.occurrence_materializer import materialize_for_schedule

class MissedOccurrencesTests(TestCase):
    def setUp(self):
        self.account = PostingAccount.objects.create(name='Test Acct', is_active=True)

    def test_startup_scan_marks_missed_correctly(self):
        # 1. Past occurrence, outside grace period (e.g., 10m ago)
        # Should be marked MISSED
        now = timezone.now()
        s1 = Schedule.objects.create(
            schedule_type=Schedule.ScheduleType.ONE_TIME,
            start_datetime=now - timedelta(minutes=10),
            timezone_name='UTC',
            content_mode='fixed_new',
            fixed_content='Missed me'
        )
        # Manually create occurrence since materialize might not create past ones
        occ1 = Occurrence.objects.create(
            schedule=s1,
            due_at=s1.start_datetime,
            display_timezone='UTC',
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )

        # 2. Past occurrence, inside grace period (e.g., 30s ago)
        # Should remain PENDING
        s2 = Schedule.objects.create(
            schedule_type=Schedule.ScheduleType.ONE_TIME,
            start_datetime=now - timedelta(seconds=30),
            timezone_name='UTC',
            content_mode='fixed_new',
            fixed_content='Catching up'
        )
        occ2 = Occurrence.objects.create(
            schedule=s2,
            due_at=s2.start_datetime,
            display_timezone='UTC',
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )

        # 3. Future occurrence
        # Should remain PENDING
        s3 = Schedule.objects.create(
            schedule_type=Schedule.ScheduleType.ONE_TIME,
            start_datetime=now + timedelta(minutes=10),
            timezone_name='UTC',
            content_mode='fixed_new',
            fixed_content='Coming up'
        )
        occ3 = Occurrence.objects.create(
            schedule=s3,
            due_at=s3.start_datetime,
            display_timezone='UTC',
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )

        # Run the scan
        count = startup_scan_missed()
        self.assertEqual(count, 1)

        occ1.refresh_from_db()
        occ2.refresh_from_db()
        occ3.refresh_from_db()

        self.assertEqual(occ1.status, Occurrence.Status.MISSED)
        self.assertEqual(occ2.status, Occurrence.Status.PENDING)
        self.assertEqual(occ3.status, Occurrence.Status.PENDING)

        # Verify HistoryEvent creation
        history = HistoryEvent.objects.filter(event_type='OCCURRENCE_MISSED')
        self.assertEqual(history.count(), 1)
        self.assertEqual(history[0].occurrence, occ1)
        self.assertEqual(history[0].schedule, s1)

    def test_recurring_schedule_continues_after_missed_occurrence(self):
        # Create a recurring schedule that started 2 hours ago, every 1 hour
        now = timezone.now()
        start_time = now - timedelta(hours=2)
        s = Schedule.objects.create(
            schedule_type=Schedule.ScheduleType.RECURRING,
            start_datetime=start_time,
            timezone_name='UTC',
            content_mode='fixed_new',
            fixed_content='Recurring text',
            interval_type=Schedule.IntervalType.HOURS,
            interval_value=1
        )
        ScheduleTargetAccount.objects.create(schedule=s, account=self.account)

        # Manually create the two past occurrences that materialized wouldn't (since they are in the past)
        # Occ 1: 2h ago (Missed)
        occ_old = Occurrence.objects.create(
            schedule=s,
            due_at=start_time,
            display_timezone='UTC',
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )
        # Occ 2: 1h ago (Missed)
        occ_mid = Occurrence.objects.create(
            schedule=s,
            due_at=start_time + timedelta(hours=1),
            display_timezone='UTC',
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )
        # Occ 3: now (due)
        # We simulate that it was NOT created yet, so materialize will create it
        # Wait, if start_time is 2h ago, and interval is 1h:
        # current_dt = start_time (2h ago)
        # hop 1 -> start_time + 1h (1h ago)
        # hop 2 -> start_time + 2h (now)
        # materialize_for_schedule only creates FUTURE occurrences (due_at > now)
        # so if we call materialize_for_schedule(s) now:
        # Occ 4: start_time + 3h (1h in future) will be created.

        materialize_for_schedule(s)
        occ_future = Occurrence.objects.filter(schedule=s, due_at__gt=now).first()
        self.assertIsNotNone(occ_future)

        # Run startup scan
        startup_scan_missed()

        occ_old.refresh_from_db()
        occ_mid.refresh_from_db()
        self.assertEqual(occ_old.status, Occurrence.Status.MISSED)
        self.assertEqual(occ_mid.status, Occurrence.Status.MISSED)

        # Execute tick
        # occ_future is not due yet.
        # But if we wait or simulate it's due
        # We want to verify that the schedule is NOT canceled
        self.assertEqual(s.status, 'active')

        # Add another occurrence that is "due" (inside grace period)
        occ_due = Occurrence.objects.create(
            schedule=s,
            due_at=now - timedelta(seconds=30),
            display_timezone='UTC',
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )

        # Tick should execute occ_due
        from unittest.mock import patch
        with patch('core.services.scheduler.execute_occurrence_attempts') as mock_exec:
            execute_scheduler_tick('test_owner')
            self.assertTrue(mock_exec.called)

        occ_due.refresh_from_db()
        self.assertEqual(occ_due.status, Occurrence.Status.EXECUTING)
        self.assertEqual(s.status, 'active')

    def test_missed_occurrences_not_retried(self):
        now = timezone.now()
        s = Schedule.objects.create(
            schedule_type=Schedule.ScheduleType.ONE_TIME,
            start_datetime=now - timedelta(minutes=10),
            timezone_name='UTC',
            content_mode='fixed_new',
            fixed_content='Past'
        )
        occ = Occurrence.objects.create(
            schedule=s,
            due_at=s.start_datetime,
            display_timezone='UTC',
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )

        startup_scan_missed()
        occ.refresh_from_db()
        self.assertEqual(occ.status, Occurrence.Status.MISSED)

        # Execute tick, should not pick up MISSED occurrence
        from unittest.mock import patch
        with patch('core.services.scheduler.execute_occurrence_attempts') as mock_exec:
            execute_scheduler_tick('test_owner')
            self.assertFalse(mock_exec.called)

        occ.refresh_from_db()
        self.assertEqual(occ.status, Occurrence.Status.MISSED)
