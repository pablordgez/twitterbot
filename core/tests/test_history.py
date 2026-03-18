from django.test import TestCase
from core.models.tweets import TweetList
from core.models.schedules import ScheduleSourceList
from core.models.accounts import PostingAccount
from core.models.schedules import Schedule
from core.models.execution import Occurrence
from core.services.history import log_event, truncate_content_summary
from core.models.history import HistoryEvent


class HistoryServiceTest(TestCase):
    def test_log_event_creates_event(self):
        event = log_event(
            event_type='TEST_EVENT',
            content_summary='Hello World',
            result_status='SUCCESS',
            detail={'some_key': 'some_value'}
        )
        self.assertEqual(HistoryEvent.objects.count(), 1)
        self.assertEqual(event.event_type, 'TEST_EVENT')
        self.assertEqual(event.content_summary, 'Hello World')
        self.assertEqual(event.result_status, 'SUCCESS')
        self.assertEqual(event.detail, {'some_key': 'some_value'})

    def test_log_event_redacts_secrets(self):
        detail = {
            'password': 'supersecretpassword',
            'normal_key': 'normal_value',
            'nested': {
                'api_key': '1234567890abcdef',
                'other': 'value'
            }
        }
        event = log_event(
            event_type='TEST_EVENT',
            detail=detail
        )
        self.assertEqual(event.detail['password'], '***REDACTED***')
        self.assertEqual(event.detail['normal_key'], 'normal_value')
        self.assertEqual(event.detail['nested']['api_key'], '***REDACTED***')
        self.assertEqual(event.detail['nested']['other'], 'value')

    def test_log_event_redacts_secrets_in_strings_and_lists(self):
        event = log_event(
            event_type='TEST_EVENT',
            detail={
                'error': 'Request failed for https://x.com/i/api/graphql/secret_query/CreateTweet token=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                'attempts': [
                    'authorization=Bearer super-secret-token',
                    {'cookie': 'auth_token=plain-secret'}
                ],
            },
        )

        self.assertNotIn('secret_query', event.detail['error'])
        self.assertNotIn('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', event.detail['error'])
        self.assertIn('[REDACTED]', event.detail['error'])
        self.assertIn('***REDACTED***', event.detail['attempts'][0])
        self.assertEqual(event.detail['attempts'][1]['cookie'], '***REDACTED***')

    def test_truncate_content_summary(self):
        short_text = "Short text"
        self.assertEqual(truncate_content_summary(short_text), "Short text")

        long_text = "a" * 150
        truncated = truncate_content_summary(long_text)
        self.assertEqual(len(truncated), 100)
        self.assertTrue(truncated.endswith('...'))

    def test_log_event_relationships(self):
        account = PostingAccount.objects.create(name='Test Account')
        schedule = Schedule.objects.create(schedule_type='one_time', content_mode='fixed', fixed_content='test', start_datetime='2024-01-01T12:00:00Z')
        occurrence = Occurrence.objects.create(schedule=schedule, due_at='2024-01-01T12:00:00Z', status='pending', display_timezone='UTC', schedule_version=1)

        event = log_event(
            event_type='LINKED_EVENT',
            account=account,
            schedule=schedule,
            occurrence=occurrence,
            correlation_id='corr-123'
        )

        self.assertEqual(event.account, account)
        self.assertEqual(event.schedule, schedule)
        self.assertEqual(event.occurrence, occurrence)
        self.assertEqual(event.correlation_id, 'corr-123')

    def test_log_event_uses_random_content_label_when_summary_missing(self):
        tweet_list = TweetList.objects.create(name='Launches')
        schedule = Schedule.objects.create(
            schedule_type='recurring',
            content_mode='random_from_list',
            start_datetime='2024-01-01T12:00:00Z',
            timezone_name='UTC',
        )
        ScheduleSourceList.objects.create(schedule=schedule, tweet_list=tweet_list)

        event = log_event(event_type='RANDOM_EVENT', schedule=schedule)

        self.assertEqual(event.content_summary, 'Random from Launches')
