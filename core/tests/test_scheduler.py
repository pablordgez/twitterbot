import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from core.models.system import SchedulerLease
from core.models.execution import Occurrence, OccurrenceAttempt
from core.models.schedules import Schedule, ScheduleTargetAccount
from core.models.accounts import PostingAccount
from core.services.scheduler import (
    acquire_or_renew_lease,
    startup_scan_missed,
    execute_scheduler_tick
)

class SchedulerTests(TestCase):
    def setUp(self):
        self.account1 = PostingAccount.objects.create(name='Acct1', is_active=True)
        self.account2 = PostingAccount.objects.create(name='Acct2', is_active=True)
        
        self.schedule = Schedule.objects.create(
            schedule_type='one_time',
            start_datetime=timezone.now() + timedelta(days=1),
            timezone_name='UTC',
            content_mode='fixed_new',
            fixed_content='Test'
        )
        ScheduleTargetAccount.objects.create(schedule=self.schedule, account=self.account1)
        ScheduleTargetAccount.objects.create(schedule=self.schedule, account=self.account2)
        
    def test_lease_acquisition_and_renewal(self):
        owner1 = uuid.uuid4().hex
        owner2 = uuid.uuid4().hex
        
        # 1. Acquire new lease
        self.assertTrue(acquire_or_renew_lease(owner1))
        lease = SchedulerLease.objects.first()
        self.assertIsNotNone(lease)
        self.assertEqual(lease.owner_id, owner1)
        self.assertTrue(lease.is_active)
        
        # 2. Renew same owner
        self.assertTrue(acquire_or_renew_lease(owner1))
        
        # 3. Different owner fails while active
        self.assertFalse(acquire_or_renew_lease(owner2))
        
        # 4. Different owner succeeds if expired
        old_time = timezone.now() - timedelta(seconds=60)
        SchedulerLease.objects.filter(pk=lease.pk).update(renewed_at=old_time)
        self.assertTrue(acquire_or_renew_lease(owner2))
        lease.refresh_from_db()
        self.assertEqual(lease.owner_id, owner2)

    def test_startup_scan_missed_occurrences(self):
        now = timezone.now()
        
        # This one should be missed (due a long time ago)
        occ1 = Occurrence.objects.create(
            schedule=self.schedule,
            due_at=now - timedelta(minutes=10),
            display_timezone="UTC",
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )
        
        # This one is pending but within grace period
        occ2 = Occurrence.objects.create(
            schedule=self.schedule,
            due_at=now - timedelta(minutes=2),
            display_timezone="UTC",
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )
        
        count = startup_scan_missed()
        self.assertEqual(count, 1)
        
        occ1.refresh_from_db()
        occ2.refresh_from_db()
        
        self.assertEqual(occ1.status, Occurrence.Status.MISSED)
        self.assertEqual(occ2.status, Occurrence.Status.PENDING)

    @patch('core.services.scheduler.refresh_rolling_horizon')
    def test_poll_and_claim_transactional(self, mock_refresh):
        now = timezone.now()
        
        occ = Occurrence.objects.create(
            schedule=self.schedule,
            due_at=now - timedelta(minutes=1),
            display_timezone="UTC",
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )
        
        owner_id = uuid.uuid4().hex
        
        # Tick should find occ, claim it, and create attempts
        success = execute_scheduler_tick(owner_id)
        self.assertTrue(success)
        
        occ.refresh_from_db()
        # Since dummy executor succeeds, it should be COMPLETED
        self.assertEqual(occ.status, Occurrence.Status.COMPLETED)
        
        attempts = OccurrenceAttempt.objects.filter(occurrence=occ)
        self.assertEqual(len(attempts), 2)
        
        # Try ticking again, should do nothing
        success = execute_scheduler_tick(owner_id)
        self.assertTrue(success)
        mock_refresh.assert_called()

    @patch('core.services.scheduler.refresh_rolling_horizon')
    def test_duplicate_execution_prevented(self, mock_refresh):
        now = timezone.now()
        
        occ = Occurrence.objects.create(
            schedule=self.schedule,
            due_at=now - timedelta(minutes=1),
            display_timezone="UTC",
            schedule_version=1,
            status=Occurrence.Status.EXECUTING # Already claimed
        )
        
        owner_id = uuid.uuid4().hex
        execute_scheduler_tick(owner_id)
        
        attempts = list(OccurrenceAttempt.objects.filter(occurrence=occ))
        self.assertEqual(len(attempts), 0)

