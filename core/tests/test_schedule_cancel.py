from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User
from core.models.schedules import Schedule
from core.models.execution import Occurrence
from core.models.history import HistoryEvent

class ScheduleCancelTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='password'
        )
        self.client = Client()
        self.client.force_login(self.admin_user)

        self.schedule = Schedule.objects.create(
            schedule_type=Schedule.ScheduleType.RECURRING,
            timezone_name='UTC',
            start_datetime=timezone.now(),
            content_mode=Schedule.ContentMode.FIXED_NEW,
            fixed_content="Test content",
            status='active'
        )
        # Create some occurrences
        self.pending_occ = Occurrence.objects.create(
            schedule=self.schedule,
            due_at=timezone.now() + timezone.timedelta(days=1),
            display_timezone='UTC',
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )
        self.completed_occ = Occurrence.objects.create(
            schedule=self.schedule,
            due_at=timezone.now() - timezone.timedelta(days=1),
            display_timezone='UTC',
            schedule_version=1,
            status=Occurrence.Status.COMPLETED
        )

    def test_cancel_schedule_marks_status(self):
        url = reverse('core:schedule_cancel', kwargs={'pk': self.schedule.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status, 'canceled')

    def test_cancel_schedule_cancels_pending_occurrences(self):
        url = reverse('core:schedule_cancel', kwargs={'pk': self.schedule.pk})
        self.client.post(url)

        self.pending_occ.refresh_from_db()
        self.assertEqual(self.pending_occ.status, Occurrence.Status.CANCELED)
        self.assertEqual(self.pending_occ.cancel_reason, 'schedule_canceled')

    def test_cancel_schedule_preserves_past_occurrences(self):
        url = reverse('core:schedule_cancel', kwargs={'pk': self.schedule.pk})
        self.client.post(url)

        self.completed_occ.refresh_from_db()
        self.assertEqual(self.completed_occ.status, Occurrence.Status.COMPLETED)

    def test_cancel_schedule_logs_audit_event(self):
        url = reverse('core:schedule_cancel', kwargs={'pk': self.schedule.pk})
        self.client.post(url)

        self.assertTrue(HistoryEvent.objects.filter(
            event_type='SCHEDULE_CANCELED',
            schedule=self.schedule
        ).exists())

    def test_cancel_schedule_only_affects_relevant_occurrences(self):
        # Create another schedule and occurrence
        other_schedule = Schedule.objects.create(
            schedule_type=Schedule.ScheduleType.ONE_TIME,
            timezone_name='UTC',
            start_datetime=timezone.now(),
            content_mode=Schedule.ContentMode.FIXED_NEW,
            fixed_content="Other content",
            status='active'
        )
        other_occ = Occurrence.objects.create(
            schedule=other_schedule,
            due_at=timezone.now() + timezone.timedelta(days=1),
            display_timezone='UTC',
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )

        url = reverse('core:schedule_cancel', kwargs={'pk': self.schedule.pk})
        self.client.post(url)

        other_occ.refresh_from_db()
        self.assertEqual(other_occ.status, Occurrence.Status.PENDING)
