from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from core.models.accounts import PostingAccount
from core.models.execution import Occurrence, OccurrenceAttempt
from core.models.schedules import Schedule, ScheduleTargetAccount, ScheduleSourceList
from core.models.tweets import TweetList, TweetEntry
from core.services.content_resolver import resolve_content_for_occurrence

class ContentResolverTests(TestCase):
    def setUp(self):
        self.account1 = PostingAccount.objects.create(name="Account 1")
        self.account2 = PostingAccount.objects.create(name="Account 2")

        self.list1 = TweetList.objects.create(name="List 1")
        self.list2 = TweetList.objects.create(name="List 2")

        self.entry1 = TweetEntry.objects.create(list=self.list1, text="Tweet A")
        self.entry2 = TweetEntry.objects.create(list=self.list1, text="Tweet B")
        self.entry3 = TweetEntry.objects.create(list=self.list2, text="Tweet C")

        self.now = timezone.now()

    def _create_schedule(self, **kwargs):
        defaults = {
            'schedule_type': Schedule.ScheduleType.ONE_TIME,
            'timezone_name': 'UTC',
            'start_datetime': self.now,
        }
        defaults.update(kwargs)
        return Schedule.objects.create(**defaults)

    def _create_occurrence(self, schedule):
        occurrence = Occurrence.objects.create(
            schedule=schedule,
            due_at=self.now,
            display_timezone='UTC',
            schedule_version=1
        )
        for target in schedule.target_accounts.all():
            OccurrenceAttempt.objects.create(
                occurrence=occurrence,
                target_account=target.account,
                automatic_attempt_seq=1
            )
        return occurrence

    def test_fixed_content(self):
        schedule = self._create_schedule(
            content_mode=Schedule.ContentMode.FIXED_NEW,
            fixed_content="Fixed Tweet"
        )
        ScheduleTargetAccount.objects.create(schedule=schedule, account=self.account1)
        ScheduleTargetAccount.objects.create(schedule=schedule, account=self.account2)

        occ = self._create_occurrence(schedule)

        resolve_content_for_occurrence(occ)

        occ.refresh_from_db()
        self.assertTrue(occ.content_resolved)
        self.assertEqual(occ.resolved_content, "Fixed Tweet")

        for attempt in occ.attempts.all():
            self.assertEqual(attempt.resolved_content, "Fixed Tweet")

    def test_random_from_list_shared(self):
        schedule = self._create_schedule(
            content_mode=Schedule.ContentMode.RANDOM_FROM_LIST,
            random_resolution_mode=Schedule.RandomResolutionMode.SHARED
        )
        ScheduleSourceList.objects.create(schedule=schedule, tweet_list=self.list1)
        ScheduleTargetAccount.objects.create(schedule=schedule, account=self.account1)
        ScheduleTargetAccount.objects.create(schedule=schedule, account=self.account2)

        occ = self._create_occurrence(schedule)

        resolve_content_for_occurrence(occ)

        occ.refresh_from_db()
        self.assertTrue(occ.content_resolved)
        self.assertIn(occ.resolved_content, ["Tweet A", "Tweet B"])

        attempts = list(occ.attempts.all())
        self.assertEqual(attempts[0].resolved_content, occ.resolved_content)
        self.assertEqual(attempts[1].resolved_content, occ.resolved_content)

    @patch('core.services.content_resolver.random.choice')
    def test_random_from_lists_per_account(self, mock_choice):
        # We will mock random.choice to return sequentially different entries
        mock_choice.side_effect = [self.entry1, self.entry3]

        schedule = self._create_schedule(
            content_mode=Schedule.ContentMode.RANDOM_FROM_LISTS,
            random_resolution_mode=Schedule.RandomResolutionMode.PER_ACCOUNT
        )
        ScheduleSourceList.objects.create(schedule=schedule, tweet_list=self.list1)
        ScheduleSourceList.objects.create(schedule=schedule, tweet_list=self.list2)

        ScheduleTargetAccount.objects.create(schedule=schedule, account=self.account1)
        ScheduleTargetAccount.objects.create(schedule=schedule, account=self.account2)

        occ = self._create_occurrence(schedule)

        resolve_content_for_occurrence(occ)

        occ.refresh_from_db()
        self.assertTrue(occ.content_resolved)
        self.assertIsNone(occ.resolved_content) # should be None for PER_ACCOUNT

        attempts = list(occ.attempts.order_by('id'))
        self.assertEqual(attempts[0].resolved_content, "Tweet A")
        self.assertEqual(attempts[1].resolved_content, "Tweet C")

        self.assertEqual(mock_choice.call_count, 2)

    def test_empty_list_handled(self):
        empty_list = TweetList.objects.create(name="Empty")
        schedule = self._create_schedule(
            content_mode=Schedule.ContentMode.RANDOM_FROM_LIST,
            random_resolution_mode=Schedule.RandomResolutionMode.SHARED
        )
        ScheduleSourceList.objects.create(schedule=schedule, tweet_list=empty_list)
        ScheduleTargetAccount.objects.create(schedule=schedule, account=self.account1)

        occ = self._create_occurrence(schedule)

        resolve_content_for_occurrence(occ)

        occ.refresh_from_db()
        self.assertTrue(occ.content_resolved)
        self.assertIsNone(occ.resolved_content)

        attempt = occ.attempts.first()
        self.assertIsNone(attempt.resolved_content)
