import json
from unittest.mock import patch, MagicMock
from django.utils import timezone
from datetime import timedelta
from django.test import TestCase

import requests

from core.models.accounts import PostingAccount, PostingAccountSecret
from core.models.schedules import Schedule
from core.models.execution import Occurrence, OccurrenceAttempt
from core.services.encryption import encrypt
from core.services.posting_executor import execute_attempt, execute_test_post

class PostingExecutorTests(TestCase):
    def setUp(self):
        self.secret_data = {
            'headers': {'authorization': 'Bearer token', 'x-csrf-token': 'csrf'},
            'cookies': {'auth_token': 'auth', 'ct0': 'ct0', 'twid': 'twid'},
            'queryId': 'query_id_123'
        }
        
        self.account = PostingAccount.objects.create(name="Test Account", is_active=True)
        PostingAccountSecret.objects.create(
            account=self.account,
            encrypted_data=encrypt(json.dumps(self.secret_data)),
            field_hash="hash"
        )
        
        self.schedule = Schedule.objects.create(
            schedule_type='one_time',
            timezone_name='UTC',
            start_datetime=timezone.now(),
            content_mode='fixed_new',
            status='active'
        )
        
        self.occurrence = Occurrence.objects.create(
            schedule=self.schedule,
            due_at=timezone.now(),
            display_timezone='UTC',
            schedule_version=1,
            status=Occurrence.Status.PENDING
        )
        
        self.attempt = OccurrenceAttempt.objects.create(
            occurrence=self.occurrence,
            target_account=self.account,
            resolved_content="Hello Twitter!"
        )

    @patch('core.services.posting_executor.requests.post')
    def test_pre_validation_rejects_missing_secrets(self, mock_post):
        self.account.secret.delete()
        self.account.refresh_from_db()
        
        execute_attempt(self.attempt)
        
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.post_result, OccurrenceAttempt.PostResult.VALIDATION_FAILED)
        self.assertFalse(self.attempt.validation_ok)
        self.assertIn("missing secrets", self.attempt.error_detail.lower())
        mock_post.assert_not_called()

    @patch('core.services.posting_executor.requests.post')
    def test_pre_validation_rejects_inactive_account(self, mock_post):
        self.account.is_active = False
        self.account.save()
        
        execute_attempt(self.attempt)
        
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.post_result, OccurrenceAttempt.PostResult.VALIDATION_FAILED)
        self.assertIn("inactive", self.attempt.error_detail.lower())
        mock_post.assert_not_called()

    @patch('core.services.posting_executor.requests.post')
    def test_pre_validation_rejects_long_tweet(self, mock_post):
        self.attempt.resolved_content = "x" * 281
        self.attempt.save()
        
        execute_attempt(self.attempt)
        
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.post_result, OccurrenceAttempt.PostResult.VALIDATION_FAILED)
        self.assertIn("length invalid", self.attempt.error_detail.lower())
        mock_post.assert_not_called()

    @patch('core.services.posting_executor.requests.post')
    def test_destination_is_hardcoded_and_tls_on(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"create_tweet": {"tweet_results": {"result": {"rest_id": "123"}}}}}
        mock_post.return_value = mock_response

        execute_attempt(self.attempt)

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://x.com/i/api/graphql/query_id_123/CreateTweet")
        self.assertTrue(kwargs.get('verify'))
        self.assertEqual(kwargs['headers'].get('content-type'), 'application/json')
        self.assertEqual(kwargs['cookies'].get('auth_token'), 'auth')
        self.assertEqual(kwargs['json']['variables']['tweet_text'], "Hello Twitter!")

        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.post_result, OccurrenceAttempt.PostResult.SUCCESS)
        self.assertTrue(self.attempt.validation_ok)

    @patch('core.services.posting_executor.requests.post')
    def test_error_details_redacted(self, mock_post):
        mock_post.side_effect = requests.exceptions.HTTPError(
            "Error calling https://x.com/i/api/graphql/my_secret_query_id_123/CreateTweet with token aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )

        execute_attempt(self.attempt)

        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.post_result, OccurrenceAttempt.PostResult.FAILED)
        self.assertNotIn("my_secret_query_id_123", self.attempt.error_detail)
        self.assertNotIn("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", self.attempt.error_detail)
        self.assertIn("[REDACTED]", self.attempt.error_detail)

    @patch('core.services.posting_executor.requests.post')
    def test_test_post_action_uses_executor(self, mock_post):
        # Simulate success
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"tweet": "ok"}}
        mock_post.return_value = mock_response

        success, error = execute_test_post(self.account, "Test tweet")

        self.assertTrue(success)
        self.assertEqual(error, "")
        
        # Simulate failure
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")
        success, error = execute_test_post(self.account, "Test tweet")

        self.assertFalse(success)
        self.assertIn("Connection failed", error)

    @patch('core.services.posting_executor.requests.post')
    def test_independence_does_not_block_others(self, mock_post):
        # Setup another account
        acc2 = PostingAccount.objects.create(name="Acc 2")
        PostingAccountSecret.objects.create(
            account=acc2, encrypted_data=encrypt(json.dumps(self.secret_data)), field_hash="2"
        )
        attempt2 = OccurrenceAttempt.objects.create(
            occurrence=self.occurrence, target_account=acc2, resolved_content="t"
        )

        # Mock first to raise an error, second to succeed
        def side_effect(*args, **kwargs):
            if mock_post.call_count == 1:
                raise requests.exceptions.Timeout("Timeout!")
            else:
                resp = MagicMock()
                resp.status_code = 200
                resp.json.return_value = {}
                return resp
                
        mock_post.side_effect = side_effect
        
        for att in [self.attempt, attempt2]:
            execute_attempt(att)
    
        self.attempt.refresh_from_db()
        attempt2.refresh_from_db()
        
        self.assertEqual(self.attempt.post_result, OccurrenceAttempt.PostResult.FAILED)
        self.assertEqual(attempt2.post_result, OccurrenceAttempt.PostResult.SUCCESS)
