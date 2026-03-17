from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from core.models.accounts import PostingAccount
from core.models.schedules import Schedule, ScheduleTargetAccount
from core.models.execution import Occurrence
from core.models.history import HistoryEvent

class OccurrenceCancelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='admin', password='testpass123')
        self.client = Client()
        self.client.force_login(self.user)
        self.account = PostingAccount.objects.create(name='TestAccount', is_active=True)
        
        self.schedule = Schedule.objects.create(
            schedule_type='one_time',
            start_datetime=timezone.now() + timedelta(days=1),
            timezone_mode='system',
            timezone_name='UTC',
            content_mode='fixed_new',
            fixed_content='Test content',
        )
        ScheduleTargetAccount.objects.create(schedule=self.schedule, account=self.account)
        
        self.occurrence = Occurrence.objects.create(
            schedule=self.schedule,
            due_at=timezone.now() + timedelta(days=1),
            display_timezone='UTC',
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )

    def test_cancel_occurrence_success(self):
        url = reverse('core:occurrence_cancel', kwargs={'pk': self.occurrence.pk})
        response = self.client.post(url)
        
        # Check redirect
        self.assertRedirects(response, reverse('core:upcoming_list'))
        
        # Check status update
        self.occurrence.refresh_from_db()
        self.assertEqual(self.occurrence.status, Occurrence.Status.CANCELED)
        self.assertEqual(self.occurrence.cancel_reason, 'manual')
        
        # Check audit log
        history = HistoryEvent.objects.filter(occurrence=self.occurrence, event_type='OCCURRENCE_CANCELED').first()
        self.assertIsNotNone(history)
        self.assertEqual(history.schedule, self.schedule)

    def test_cancel_requires_post(self):
        url = reverse('core:occurrence_cancel', kwargs={'pk': self.occurrence.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405) # Method Not Allowed

    def test_cancel_requires_login(self):
        self.client.logout()
        url = reverse('core:occurrence_cancel', kwargs={'pk': self.occurrence.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_cannot_cancel_non_pending(self):
        # Already completed
        self.occurrence.status = Occurrence.Status.COMPLETED
        self.occurrence.save()
        
        url = reverse('core:occurrence_cancel', kwargs={'pk': self.occurrence.pk})
        response = self.client.post(url)
        
        # Should either error or do nothing. According to spec, only pending can be canceled.
        # Let's assume we redirect back with a message or just don't change it.
        # Implementation will probably use a 404 or a redirect if the queryset filters status=PENDING.
        
        self.occurrence.refresh_from_db()
        self.assertEqual(self.occurrence.status, Occurrence.Status.COMPLETED)

    def test_cancel_nonexistent_occurrence(self):
        url = reverse('core:occurrence_cancel', kwargs={'pk': 9999})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)
