from django.test import TestCase
from django.utils import timezone
from core.models.accounts import PostingAccount
from core.models.execution import Occurrence, OccurrenceAttempt, RecurringUsageState
from core.models.schedules import Schedule, ScheduleTargetAccount, ScheduleSourceList
from core.models.tweets import TweetList, TweetEntry
from core.models.history import HistoryEvent
from core.services.content_resolver import resolve_content_for_occurrence
from core.services.posting_executor import execute_attempt

class ReuseExhaustionTests(TestCase):
    def setUp(self):
        self.account = PostingAccount.objects.create(name="Account 1", is_active=True)
        # We need a secret for posting executor not to fail validation.
        # But we can just mock _execute_post in testing executor or just test resolver.
        # Actually, let's just test resolver primarily for exhaustion.

        self.list1 = TweetList.objects.create(name="List 1")
        self.entry1 = TweetEntry.objects.create(list=self.list1, text="Tweet A")
        self.entry2 = TweetEntry.objects.create(list=self.list1, text="Tweet B")

        self.now = timezone.now()

    def _create_schedule(self, exhaustion_behavior):
        schedule = Schedule.objects.create(
            schedule_type=Schedule.ScheduleType.RECURRING,
            timezone_name='UTC',
            start_datetime=self.now,
            content_mode=Schedule.ContentMode.RANDOM_FROM_LIST,
            random_resolution_mode=Schedule.RandomResolutionMode.SHARED,
            reuse_enabled=False,
            exhaustion_behavior=exhaustion_behavior
        )
        ScheduleSourceList.objects.create(schedule=schedule, tweet_list=self.list1)
        ScheduleTargetAccount.objects.create(schedule=schedule, account=self.account)
        return schedule

    def _create_occurrence(self, schedule):
        occurrence = Occurrence.objects.create(
            schedule=schedule,
            due_at=self.now,
            display_timezone='UTC',
            schedule_version=1
        )
        OccurrenceAttempt.objects.create(
            occurrence=occurrence,
            target_account=self.account,
            automatic_attempt_seq=1
        )
        return occurrence

    def test_used_tweets_excluded(self):
        schedule = self._create_schedule(Schedule.ExhaustionBehavior.SKIP)
        # Mark entry1 as used
        RecurringUsageState.objects.create(schedule=schedule, tweet_entry=self.entry1)

        occ = self._create_occurrence(schedule)
        resolve_content_for_occurrence(occ)

        occ.refresh_from_db()
        self.assertEqual(occ.resolved_content, "Tweet B")
        self.assertEqual(occ.resolved_tweet_entry, self.entry2)

    def test_exhaustion_skip(self):
        schedule = self._create_schedule(Schedule.ExhaustionBehavior.SKIP)
        RecurringUsageState.objects.create(schedule=schedule, tweet_entry=self.entry1)
        RecurringUsageState.objects.create(schedule=schedule, tweet_entry=self.entry2)

        occ = self._create_occurrence(schedule)
        resolve_content_for_occurrence(occ)

        occ.refresh_from_db()
        self.assertEqual(occ.status, Occurrence.Status.SKIPPED)
        self.assertEqual(occ.cancel_reason, "all tweets exhausted – skip until more added")

        event = HistoryEvent.objects.filter(occurrence=occ, event_type='OCCURRENCE_EXECUTION_BLOCKED').first()
        self.assertIsNotNone(event)
        self.assertEqual(event.result_status, Occurrence.Status.SKIPPED)
        self.assertEqual(event.detail['reason'], "all tweets exhausted – skip until more added")

    def test_exhaustion_stop(self):
        schedule = self._create_schedule(Schedule.ExhaustionBehavior.STOP)
        RecurringUsageState.objects.create(schedule=schedule, tweet_entry=self.entry1)
        RecurringUsageState.objects.create(schedule=schedule, tweet_entry=self.entry2)

        occ = self._create_occurrence(schedule)
        resolve_content_for_occurrence(occ)

        occ.refresh_from_db()
        self.assertEqual(occ.status, Occurrence.Status.SKIPPED)
        self.assertEqual(occ.cancel_reason, "all tweets exhausted – stop")

        event = HistoryEvent.objects.filter(occurrence=occ, event_type='OCCURRENCE_EXECUTION_BLOCKED').first()
        self.assertIsNotNone(event)
        self.assertEqual(event.content_summary, "all tweets exhausted – stop")

    def test_exhaustion_reset(self):
        schedule = self._create_schedule(Schedule.ExhaustionBehavior.RESET)
        RecurringUsageState.objects.create(schedule=schedule, tweet_entry=self.entry1)
        RecurringUsageState.objects.create(schedule=schedule, tweet_entry=self.entry2)

        occ = self._create_occurrence(schedule)
        resolve_content_for_occurrence(occ)

        occ.refresh_from_db()
        self.assertTrue(occ.content_resolved)
        # Should reset and pick one of the two
        self.assertIn(occ.resolved_content, ["Tweet A", "Tweet B"])
        # States should be cleared
        self.assertEqual(RecurringUsageState.objects.filter(schedule=schedule).count(), 0)

    def test_executor_records_usage_on_success(self):
        from unittest.mock import patch

        schedule = self._create_schedule(Schedule.ExhaustionBehavior.SKIP)
        occ = self._create_occurrence(schedule)

        # Resolve content first
        resolve_content_for_occurrence(occ)
        occ.refresh_from_db()

        attempt = occ.attempts.first()

        # Mock _execute_post to return success
        with patch('core.services.posting_executor._execute_post') as mock_post:
            mock_post.return_value = (True, "", {})
            from core.models.accounts import PostingAccountSecret

            # We also need to mock secret validation to pass
            PostingAccountSecret.objects.create(
                account=attempt.target_account,
                encrypted_data=b'abc',
                field_hash='hash'
            )

            with patch('core.services.posting_executor.decrypt') as mock_decrypt:
                mock_decrypt.return_value = '{"queryId": "123"}'
                execute_attempt(attempt)
        attempt.refresh_from_db()
        print(f"Error detail: {attempt.error_detail}")
        self.assertEqual(attempt.post_result, OccurrenceAttempt.PostResult.SUCCESS)

        # Verify usage state was created
        usage = RecurringUsageState.objects.filter(schedule=schedule).first()
        self.assertIsNotNone(usage)
        self.assertEqual(usage.tweet_entry_id, attempt.resolved_tweet_entry_id)
