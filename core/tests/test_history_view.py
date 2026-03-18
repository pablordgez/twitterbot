from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from core.models import HistoryEvent, PostingAccount, Schedule
from datetime import timedelta
from django.utils import timezone

class TestHistoryView(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'admin@example.com', 'password')
        self.client.force_login(self.user)
        
    def test_history_view_requires_login(self):
        self.client.logout()
        url = reverse('core:history_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_history_list_renders(self):
        HistoryEvent.objects.create(event_type='TEST_EVENT', content_summary='Hello', result_status='success')
        url = reverse('core:history_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('TEST_EVENT', response.content.decode())

    def test_history_filters(self):
        account = PostingAccount.objects.create(name='Test Account')
        HistoryEvent.objects.create(event_type='EVENT_1', account=account, result_status='success')
        HistoryEvent.objects.create(event_type='EVENT_2', result_status='failed')
        
        url = reverse('core:history_list')
        
        # Filter by account
        response = self.client.get(url, {'account': account.id})
        content = response.content.decode()
        self.assertIn('EVENT_1', content)
        self.assertNotIn('EVENT_2', content)
        
        # Filter by status
        response = self.client.get(url, {'status': 'failed'})
        content = response.content.decode()
        self.assertIn('EVENT_2', content)
        self.assertNotIn('EVENT_1', content)
        
        # Search text
        response = self.client.get(url, {'search': 'EVENT_1'})
        content = response.content.decode()
        self.assertIn('EVENT_1', content)
        self.assertNotIn('EVENT_2', content)

    def test_history_date_range_filter(self):
        event_old = HistoryEvent.objects.create(event_type='OLD_EVENT')
        event_old.timestamp = timezone.now() - timedelta(days=5)
        event_old.save()
        
        event_new = HistoryEvent.objects.create(event_type='NEW_EVENT')
        event_new.timestamp = timezone.now()
        event_new.save()
        
        url = reverse('core:history_list')
        yesterday_str = (timezone.now() - timedelta(days=1)).date().isoformat()
        
        # Filter from yesterday
        response = self.client.get(url, {'date_from': yesterday_str})
        content = response.content.decode()
        self.assertIn('NEW_EVENT', content)
        self.assertNotIn('OLD_EVENT', content)
        
        # Filter to yesterday
        response = self.client.get(url, {'date_to': yesterday_str})
        content = response.content.decode()
        self.assertIn('OLD_EVENT', content)
        self.assertNotIn('NEW_EVENT', content)

    def test_history_detail_row(self):
        event = HistoryEvent.objects.create(
            event_type='TEST_DETAIL',
            detail={'error': 'some error msg'}
        )
        url = reverse('core:history_detail_row', kwargs={'pk': event.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('some error msg', content)
        self.assertIn('TEST_DETAIL', content)

    def test_xss_prevention(self):
        HistoryEvent.objects.create(
            event_type='XSS_TEST',
            content_summary='<script>alert(1)</script>',
            detail={'msg': '<script>alert(2)</script>'}
        )
        
        url = reverse('core:history_list')
        response = self.client.get(url)
        content = response.content.decode()
        # Escaped in list view
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', content)
        self.assertNotIn('<script>alert(1)</script>', content)
        
        event = HistoryEvent.objects.first()
        url_detail = reverse('core:history_detail_row', kwargs={'pk': event.pk})
        response_detail = self.client.get(url_detail)
        detail_content = response_detail.content.decode()
        
        # Check if XSS is escaped in JSON rendering or summary rendering
        self.assertNotIn('<script>alert(2)</script>', detail_content)
        self.assertIn('&lt;script&gt;alert(2)&lt;/script&gt;', detail_content)
