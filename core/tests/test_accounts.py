import json
import hashlib
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from django.test import TestCase, Client
from unittest.mock import patch, MagicMock

from core.models.accounts import PostingAccount, PostingAccountSecret
from core.models.schedules import Schedule, ScheduleTargetAccount
from core.models.history import HistoryEvent
from core.services.encryption import get_fernet_instance

User = get_user_model()

class AccountTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser('admin', 'admin@test.com', 'password')
        self.client = Client()
        self.client.force_login(self.admin_user)

        self.account = PostingAccount.objects.create(name="Test Account", is_active=True)

        self.active_schedule = Schedule.objects.create(
            schedule_type='one_time',
            timezone_name='UTC',
            start_datetime=timezone.now() + timedelta(days=1),
            content_mode='fixed_new',
            status='active'
        )

    def test_account_list(self):
        url = reverse('core:account_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Test Account", str(response.content))

    def test_account_create(self):
        url = reverse('core:account_create')
        response = self.client.post(url, {
            'name': 'New Account',
            'is_active': True,
            'notification_mode': 'none'
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(PostingAccount.objects.filter(name='New Account').exists())
        self.assertTrue(HistoryEvent.objects.filter(event_type='ACCOUNT_CREATED', account__name='New Account').exists())

    def test_account_update(self):
        url = reverse('core:account_update', kwargs={'pk': self.account.pk})
        response = self.client.post(url, {
            'name': 'Updated Name',
            'is_active': False,
            'notification_mode': 'every_failure'
        })
        self.assertEqual(response.status_code, 302)
        self.account.refresh_from_db()
        self.assertEqual(self.account.name, 'Updated Name')
        self.assertFalse(self.account.is_active)
        self.assertTrue(HistoryEvent.objects.filter(event_type='ACCOUNT_UPDATED', account=self.account).exists())

    def test_account_detail_masked_secret(self):
        json_data = json.dumps({"test": "data"})
        f = get_fernet_instance()
        enc = f.encrypt(json_data.encode('utf-8'))
        fh = hashlib.sha256(json_data.encode('utf-8')).hexdigest()

        PostingAccountSecret.objects.create(account=self.account, encrypted_data=enc, field_hash=fh)

        url = reverse('core:account_detail', kwargs={'pk': self.account.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        masked = f"••••••{fh[-4:]}"
        self.assertIn(masked, response.content.decode('utf-8'))
        self.assertIn("Credentials Configured", str(response.content))

    def test_account_delete_cascade_schedules(self):
        ScheduleTargetAccount.objects.create(schedule=self.active_schedule, account=self.account)

        url = reverse('core:account_delete', kwargs={'pk': self.account.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Warning: Dependency Impact", str(response.content))

        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PostingAccount.objects.filter(id=self.account.id).exists())

        self.active_schedule.refresh_from_db()
        self.assertEqual(self.active_schedule.status, 'canceled')

    def test_curl_import_valid(self):
        curl_input = "curl 'https://x.com/i/api/graphql/TEST_QID/CreateTweet' -H 'authorization: Bearer A' -H 'x-csrf-token: B' -b 'auth_token=C; ct0=D; twid=E'"
        url = reverse('core:account_import', kwargs={'pk': self.account.pk})
        response = self.client.post(url, {'curl_text': curl_input})
        self.assertEqual(response.status_code, 302)

        self.account.refresh_from_db()
        self.assertTrue(hasattr(self.account, 'secret'))

        event = HistoryEvent.objects.filter(account=self.account).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, 'ACCOUNT_IMPORT_ACCEPTED')

    @patch('core.services.posting_executor.requests.post')
    def test_test_post_requires_csrf_post(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"tweet": "ok"}}
        mock_post.return_value = mock_response

        url = reverse('core:account_test_post', kwargs={'pk': self.account.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

        secret_data = {
            'headers': {'authorization': 'Bearer token', 'x-csrf-token': 'csrf'},
            'cookies': {'auth_token': 'auth', 'ct0': 'ct0', 'twid': 'twid'},
            'queryId': 'query_id_123'
        }
        json_enc = get_fernet_instance().encrypt(json.dumps(secret_data).encode('utf-8'))
        PostingAccountSecret.objects.create(account=self.account, encrypted_data=json_enc, field_hash="1")

        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(HistoryEvent.objects.filter(event_type='TEST_POST_CONFIRMED').exists())
        outcome = HistoryEvent.objects.filter(event_type='TEST_POST_SUCCEEDED').first()
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.content_summary, 'test')
        self.assertTrue(
            HistoryEvent.objects.filter(
                event_type='TEST_POST_CONFIRMED',
                correlation_id=outcome.correlation_id,
            ).exists()
        )
