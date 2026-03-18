from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from core.models.accounts import PostingAccount
from core.models.schedules import Schedule
from core.models.execution import Occurrence
from core.models.history import HistoryEvent
import datetime

class DashboardViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='admin', password='password', email='admin@example.com')
        # Need to go to login first to bypass FirstRunMiddleware in some contexts or just to get CSRF
        self.client.post(reverse('core:login'), {
            'username': 'admin',
            'password': 'password'
        })
        
        # Create some data
        self.account = PostingAccount.objects.create(name='Test Account')
        self.schedule = Schedule.objects.create(
            schedule_type=Schedule.ScheduleType.ONE_TIME,
            start_datetime=timezone.now() + datetime.timedelta(days=1),
            content_mode=Schedule.ContentMode.FIXED_NEW,
            fixed_content='Test tweet',
            timezone_name='UTC',
            status='active'
        )
        self.occurrence = Occurrence.objects.create(
            schedule=self.schedule,
            due_at=timezone.now() + datetime.timedelta(hours=1),
            display_timezone='UTC',
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )
        self.history = HistoryEvent.objects.create(
            event_type='POST_ATTEMPT_SUCCEEDED',
            result_status='success',
            content_summary='Success tweet'
        )

    def test_dashboard_access_required_login(self):
        self.client.logout()
        response = self.client.get(reverse('core:dashboard'))
        self.assertNotEqual(response.status_code, 200)

    def test_dashboard_renders_correct_stats(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1 Accounts')
        self.assertContains(response, '1 Active Schedules')
        self.assertContains(response, 'Next Upcoming Post')
        self.assertContains(response, 'POST_ATTEMPT_SUCCEEDED')
        self.assertContains(response, 'Success tweet')

    def test_dashboard_no_upcoming_occurrences(self):
        Occurrence.objects.all().delete()
        response = self.client.get(reverse('core:dashboard'))
        self.assertContains(response, 'No upcoming occurrences.')

    def test_dashboard_no_recent_activity(self):
        HistoryEvent.objects.all().delete()
        response = self.client.get(reverse('core:dashboard'))
        self.assertContains(response, 'No recent activity.')
