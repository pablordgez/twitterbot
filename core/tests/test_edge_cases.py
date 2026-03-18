from django.test import TestCase
from django.utils import timezone
from datetime import timedelta, datetime
from zoneinfo import ZoneInfo
import random

from core.models.accounts import PostingAccount
from core.models.schedules import Schedule
from core.models.execution import Occurrence
from core.services.scheduler import startup_scan_missed
from core.services.occurrence_materializer import materialize_for_schedule

class EdgeCasesTests(TestCase):
    def test_missed_occurrence_on_restart(self):
        """Test that occurrences past grace period are marked MISSED."""
        schedule = Schedule.objects.create(
            schedule_type='one_time',
            content_mode='fixed_new',
            fixed_content='Missed test',
            start_datetime=timezone.now() - timedelta(minutes=5),
            timezone_name='UTC'
        )
        # Materializer generates occurrence in the past
        materialize_for_schedule(schedule)
        
        occ = Occurrence.objects.get(schedule=schedule)
        self.assertEqual(occ.status, Occurrence.Status.PENDING)
        
        # Simulate restart
        startup_scan_missed()
        
        occ.refresh_from_db()
        self.assertEqual(occ.status, Occurrence.Status.MISSED)

    from unittest.mock import patch
    @patch('core.services.occurrence_materializer.timezone.now')
    def test_dst_boundary_scheduling(self, mock_now):
        """Test scheduling across a DST boundary.
        US/Eastern DST ends first Sunday in November.
        In 2023, DST ends on Nov 5 at 2:00 AM.
        We schedule at 1:30 AM every day.
        """
        # Nov 4, 2023 1:30 AM EDT
        eastern = ZoneInfo('US/Eastern')
        dt_start = datetime(2023, 11, 4, 1, 30, tzinfo=eastern)
        
        mock_now.return_value = datetime(2023, 11, 3, 12, 0, tzinfo=ZoneInfo("UTC"))
        
        schedule = Schedule.objects.create(
            schedule_type='recurring',
            interval_type='days',
            interval_value=1,
            content_mode='fixed_new',
            fixed_content='DST Test',
            start_datetime=dt_start,
            timezone_name='US/Eastern'
        )
        
        materialize_for_schedule(schedule)
        
        occs = list(Occurrence.objects.filter(schedule=schedule).order_by('due_at')[:3])
        
        # Occurrence 1: Nov 4, 1:30 AM EDT (-0400) -> 5:30 AM UTC
        self.assertEqual(occs[0].due_at.strftime('%Y-%m-%d %H:%M:%S'), '2023-11-04 05:30:00')
        
        # Occurrence 2: Nov 5, 1:30 AM EST? Wait, at 1:30 AM on Nov 5, it happens twice.
        # `zoneinfo` or `pytz` handles it, let's just check the local time remains 1:30
        self.assertEqual(occs[1].due_at.astimezone(eastern).strftime('%H:%M'), '01:30')
        
        # Occurrence 3: Nov 6, 1:30 AM EST (-0500) -> 6:30 AM UTC
        self.assertEqual(occs[2].due_at.strftime('%Y-%m-%d %H:%M:%S'), '2023-11-06 06:30:00')
