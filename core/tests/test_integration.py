from unittest.mock import patch
from datetime import timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core import mail
from core.models.accounts import PostingAccount
from core.models.tweets import TweetList, TweetEntry
from core.models.schedules import Schedule
from core.models.execution import Occurrence, OccurrenceAttempt
from core.models.history import HistoryEvent
from core.models.notifications import SMTPSettings, NotificationRecipient

class FullIntegrationTests(TestCase):
    @patch('core.services.posting_executor.requests.post')
    def test_full_lifecycle(self, mock_post):
        # 1. Setup
        client = Client()
        response = client.post(reverse('core:setup'), {
            'username': 'admin',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        self.assertEqual(response.status_code, 302)

        # 2. Login
        from django.contrib.auth.models import User
        user = User.objects.get(username='admin')
        client.force_login(user)

        # 3. Create Account
        response = client.post(reverse('core:account_create'), {
            'name': 'Test Integration Account',
            'is_active': True,
            'notification_mode': 'every_failure'
        })
        self.assertEqual(response.status_code, 302)
        account = PostingAccount.objects.get(name='Test Integration Account')

        # 4. Import cURL
        curl_text = '''curl 'https://twitter.com/i/api/graphql/xxx/CreateTweet' -H 'authorization: Bearer test_token' -H 'x-csrf-token: test_csrf' -H 'cookie: auth_token=test_cookie; twid=u%3D123; ct0=test_csrf' --data-raw '{"variables":{"tweet_text":"test"}}' '''
        response = client.post(reverse('core:account_import', kwargs={'pk': account.pk}), {
            'curl_text': curl_text
        })
        if response.status_code != 302:
            print(response.content.decode('utf-8'))
        self.assertEqual(response.status_code, 302)
        account.refresh_from_db()
        self.assertIsNotNone(account.secret)

        # Configure SMTP
        SMTPSettings.objects.create(host='smtp.example.com', port=587, sender_email='bot@example.com')
        NotificationRecipient.objects.create(email='admin@example.com')

        # 5. Create Tweet List & Import CSV (Mocked via service call or form post)
        list_response = client.post(reverse('core:tweet_list_create'), {
            'name': 'Promo List'
        })
        self.assertEqual(list_response.status_code, 302)
        tweet_list = TweetList.objects.get(name='Promo List')

        csv_response = client.post(reverse('core:csv_import', kwargs={'list_pk': tweet_list.pk}), {
            'import_mode': 'paste',
            'target_list': tweet_list.pk,
            'csv_text': 'Promo tweet 1\nPromo tweet 2'
        })
        self.assertEqual(csv_response.status_code, 200) # FormView renders success directly or redirects
        self.assertTrue(TweetEntry.objects.filter(list=tweet_list).count() >= 2)

        # 6. Create Schedule
        due_time = timezone.now() - timedelta(minutes=1) # due immediately
        sched_response = client.post(reverse('core:schedule_create'), {
            'schedule_type': 'one_time',
            'target_accounts': [account.pk],
            'timezone_mode': 'utc',
            'start_datetime': due_time.strftime('%Y-%m-%dT%H:%M:%S'),
            'content_mode': 'random_from_list',
            'source_lists': [tweet_list.pk],
        })
        self.assertEqual(sched_response.status_code, 302)
        schedule = Schedule.objects.first()

        # Ensure occurrence materialized
        occurrence = Occurrence.objects.filter(schedule=schedule).first()
        self.assertIsNotNone(occurrence)
        self.assertEqual(occurrence.status, Occurrence.Status.PENDING)

        # 7. Scheduler Claims and Executes (mock post response)
        mock_post.return_value.status_code = 401 # Simulate failure to trigger notification
        mock_post.return_value.json.return_value = {"errors": [{"message": "Unauthorized"}]}

        from core.services.scheduler import execute_scheduler_tick
        success = execute_scheduler_tick(owner_id="test_owner")
        self.assertTrue(success)

        # Verification
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.status, Occurrence.Status.FAILED)

        attempt = OccurrenceAttempt.objects.get(occurrence=occurrence)
        self.assertEqual(attempt.post_result, OccurrenceAttempt.PostResult.FAILED)
        self.assertTrue(attempt.notification_sent)

        # History logged
        failure_log = HistoryEvent.objects.filter(event_type='POST_ATTEMPT_FAILED').first()
        self.assertIsNotNone(failure_log)

        # Notification sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Posting Failure', mail.outbox[0].subject)

