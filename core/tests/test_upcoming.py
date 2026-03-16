from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from core.models.accounts import PostingAccount
from core.models.tweets import TweetList
from core.models.schedules import Schedule
from core.models.schedules import Schedule, ScheduleTargetAccount, ScheduleSourceList
from core.models.execution import Occurrence

class UpcomingViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='admin', password='testpass123')
        self.client = Client()
        self.client.force_login(self.user)
        self.account = PostingAccount.objects.create(name='TestAccount', is_active=True)
        
    def _create_schedule(self, content_mode='fixed_new', **kwargs):
        defaults = {
            'schedule_type': 'one_time',
            'start_datetime': timezone.now() + timedelta(days=1),
            'timezone_mode': 'system',
            'timezone_name': 'UTC',
            'content_mode': content_mode,
            'fixed_content': 'Fixed text',
        }
        source_list = kwargs.pop('source_list', None)
        defaults.update(kwargs)
        schedule = Schedule.objects.create(**defaults)
        ScheduleTargetAccount.objects.create(schedule=schedule, account=self.account)
        if source_list:
            ScheduleSourceList.objects.create(schedule=schedule, tweet_list=source_list)
        return schedule
        
    def test_upcoming_view_requires_login(self):
        client = Client()
        url = reverse('core:upcoming_list')
        response = client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_upcoming_view_shows_pending_ordered(self):
        schedule1 = self._create_schedule()
        schedule2 = self._create_schedule()
        
        occ2 = Occurrence.objects.create(
            schedule=schedule2,
            due_at=timezone.now() + timedelta(days=2),
            display_timezone="UTC",
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )
        occ1 = Occurrence.objects.create(
            schedule=schedule1,
            due_at=timezone.now() + timedelta(days=1),
            display_timezone="UTC",
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )
        # Should not be included
        occ3 = Occurrence.objects.create(
            schedule=schedule1,
            due_at=timezone.now() + timedelta(days=3),
            display_timezone="UTC",
            schedule_version=1,
            status=Occurrence.Status.COMPLETED
        )
        
        url = reverse('core:upcoming_list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        occurrences = list(response.context['object_list'])
        
        self.assertEqual(len(occurrences), 2)
        self.assertEqual(occurrences[0], occ1)
        self.assertEqual(occurrences[1], occ2)

    def test_upcoming_view_content_display_fixed(self):
        schedule = self._create_schedule(content_mode='fixed_new', fixed_content="Test fixed content")
        
        Occurrence.objects.create(
            schedule=schedule,
            due_at=timezone.now() + timedelta(days=1),
            display_timezone="UTC",
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )
        
        url = reverse('core:upcoming_list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test fixed content")

    def test_upcoming_view_content_display_random(self):
        tweet_list = TweetList.objects.create(name="My List")
        schedule = self._create_schedule(content_mode='random_from_list', source_list=tweet_list)
        
        Occurrence.objects.create(
            schedule=schedule,
            due_at=timezone.now() + timedelta(days=1),
            display_timezone="UTC",
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )
        
        url = reverse('core:upcoming_list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Random from: My List")
