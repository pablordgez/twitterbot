from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from core.models.tweets import TweetList
from core.models.schedules import Schedule, ScheduleSourceList

User = get_user_model()

class TweetListTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'admin@test.com', 'password')
        self.client = Client()
        self.client.force_login(self.user)
        self.tweet_list = TweetList.objects.create(name="Test List")

    def test_tweet_list_list(self):
        url = reverse('core:tweet_list_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test List")

    def test_tweet_list_create(self):
        url = reverse('core:tweet_list_create')
        response = self.client.post(url, {'name': 'New List'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(TweetList.objects.filter(name='New List').exists())

    def test_tweet_list_update(self):
        url = reverse('core:tweet_list_update', kwargs={'pk': self.tweet_list.pk})
        response = self.client.post(url, {'name': 'Updated List'})
        self.assertEqual(response.status_code, 302)
        self.tweet_list.refresh_from_db()
        self.assertEqual(self.tweet_list.name, 'Updated List')

    def test_tweet_list_delete_no_dependencies(self):
        url = reverse('core:tweet_list_delete', kwargs={'pk': self.tweet_list.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(TweetList.objects.filter(pk=self.tweet_list.pk).exists())

    def test_tweet_list_delete_with_dependencies(self):
        active_schedule = Schedule.objects.create(
            schedule_type='one_time',
            start_datetime=timezone.now() + timedelta(days=1),
            content_mode='fixed_from_list',
            status='active',
            timezone_name='UTC'
        )
        ScheduleSourceList.objects.create(schedule=active_schedule, tweet_list=self.tweet_list)

        url = reverse('core:tweet_list_delete', kwargs={'pk': self.tweet_list.pk})
        # GET shows warnings
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Warning: Dependency Impact")
        self.assertContains(response, f"Schedule ID #{active_schedule.id}")

        # POST deletes and cancels schedules
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(TweetList.objects.filter(pk=self.tweet_list.pk).exists())

        active_schedule.refresh_from_db()
        self.assertEqual(active_schedule.status, 'canceled')

    def test_tweet_list_xss_safety(self):
        xss_payload = "<script>alert('xss')</script>"
        TweetList.objects.create(name=xss_payload)

        url = reverse('core:tweet_list_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;")
        self.assertNotContains(response, xss_payload)
