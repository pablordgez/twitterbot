import json
import hashlib
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from django.test import TestCase, Client
from unittest.mock import patch, MagicMock

from core.forms.accounts import BrowserSessionStateForm
from core.models.accounts import PostingAccount, PostingAccountSecret, PostingAccountBrowserCredential
from core.models.schedules import Schedule, ScheduleTargetAccount
from core.models.history import HistoryEvent
from core.services.encryption import get_fernet_instance, decrypt

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
            'auth_mode': 'request',
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
            'auth_mode': 'browser',
            'is_active': False,
            'notification_mode': 'every_failure'
        })
        self.assertEqual(response.status_code, 302)
        self.account.refresh_from_db()
        self.assertEqual(self.account.name, 'Updated Name')
        self.assertEqual(self.account.auth_mode, PostingAccount.AuthMode.BROWSER)
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

    def test_browser_credentials_save(self):
        url = reverse('core:account_browser_credentials', kwargs={'pk': self.account.pk})
        response = self.client.post(url, {
            'username': 'user@example.com',
            'password': 'super-secret-password',
        })
        self.assertEqual(response.status_code, 302)

        self.account.refresh_from_db()
        self.assertEqual(self.account.auth_mode, PostingAccount.AuthMode.BROWSER)
        self.assertTrue(hasattr(self.account, 'browser_credential'))

        creds = PostingAccountBrowserCredential.objects.get(account=self.account)
        self.assertEqual(decrypt(creds.encrypted_username), 'user@example.com')
        self.assertEqual(decrypt(creds.encrypted_password), 'super-secret-password')
        self.assertTrue(
            HistoryEvent.objects.filter(
                event_type='ACCOUNT_BROWSER_CREDENTIALS_SAVED',
                account=self.account,
            ).exists()
        )

    def test_browser_session_state_save(self):
        url = reverse('core:account_browser_session', kwargs={'pk': self.account.pk})
        response = self.client.post(url, {
            'storage_state': '{"cookies": [{"name": "auth_token", "value": "A", "domain": ".x.com", "path": "/"}], "origins": []}',
        })
        self.assertEqual(response.status_code, 302)

        self.account.refresh_from_db()
        self.assertEqual(self.account.auth_mode, PostingAccount.AuthMode.BROWSER)
        creds = PostingAccountBrowserCredential.objects.get(account=self.account)
        self.assertEqual(
            json.loads(decrypt(creds.encrypted_storage_state)),
            {
                'cookies': [{
                    'name': 'auth_token',
                    'value': 'A',
                    'domain': '.x.com',
                    'path': '/',
                    'expires': -1,
                    'httpOnly': False,
                    'secure': True,
                    'sameSite': 'None',
                }],
                'origins': [],
            },
        )
        self.assertTrue(
            HistoryEvent.objects.filter(
                event_type='ACCOUNT_BROWSER_SESSION_SAVED',
                account=self.account,
            ).exists()
        )

    def test_browser_session_state_save_cookie_header(self):
        url = reverse('core:account_browser_session', kwargs={'pk': self.account.pk})
        response = self.client.post(url, {
            'storage_state': 'Cookie: auth_token=AUTH; ct0=CSRF; twid=TWID',
        })
        self.assertEqual(response.status_code, 302)

        creds = PostingAccountBrowserCredential.objects.get(account=self.account)
        saved_state = json.loads(decrypt(creds.encrypted_storage_state))
        self.assertEqual(saved_state['origins'], [])
        self.assertEqual(
            [cookie['name'] for cookie in saved_state['cookies']],
            ['auth_token', 'ct0', 'twid'],
        )
        self.assertTrue(all(cookie['domain'] == '.x.com' for cookie in saved_state['cookies']))

    @patch('core.services.posting_executor.requests.post')
    def test_test_post_requires_csrf_post(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"create_tweet": {"tweet_results": {"result": {"rest_id": "123"}}}}
        }
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


class BrowserSessionStateFormTests(TestCase):
    def test_accepts_cookie_array_json(self):
        form = BrowserSessionStateForm(data={
            'storage_state': '[{"name":"auth_token","value":"A","domain":".x.com","path":"/"}]',
        })

        self.assertTrue(form.is_valid(), form.errors)
        cleaned = json.loads(form.cleaned_data['storage_state'])
        self.assertEqual(cleaned['origins'], [])
        self.assertEqual(cleaned['cookies'][0]['name'], 'auth_token')
        self.assertEqual(cleaned['cookies'][0]['sameSite'], 'None')

    def test_accepts_cookie_map_json(self):
        form = BrowserSessionStateForm(data={
            'storage_state': '{"auth_token":"A","ct0":"B"}',
        })

        self.assertTrue(form.is_valid(), form.errors)
        cleaned = json.loads(form.cleaned_data['storage_state'])
        self.assertEqual(
            [cookie['name'] for cookie in cleaned['cookies']],
            ['auth_token', 'ct0'],
        )

    def test_accepts_raw_cookie_header(self):
        form = BrowserSessionStateForm(data={
            'storage_state': 'auth_token=A; ct0=B; twid=C',
        })

        self.assertTrue(form.is_valid(), form.errors)
        cleaned = json.loads(form.cleaned_data['storage_state'])
        self.assertEqual(len(cleaned['cookies']), 3)
        self.assertEqual(cleaned['cookies'][0]['domain'], '.x.com')

    def test_rejects_invalid_session_import(self):
        form = BrowserSessionStateForm(data={
            'storage_state': '{"cookies":{"bad":"shape"}}',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('Cookies must be an array.', form.errors['storage_state'][0])
