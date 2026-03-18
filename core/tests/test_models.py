from django.test import TestCase
from django.db import IntegrityError
from core.models import (
    PostingAccount, PostingAccountSecret, TweetList, TweetEntry, Schedule,
    ScheduleTargetAccount, ScheduleSourceList, Occurrence, OccurrenceAttempt
)
from django.utils import timezone

class TestPostingAccount(TestCase):
    def test_create_account(self):
        acc = PostingAccount.objects.create(name="Test Account")
        self.assertEqual(acc.name, "Test Account")
        self.assertTrue(acc.is_active)
        self.assertEqual(acc.notification_mode, PostingAccount.NotificationMode.FIRST_FAILURE)

        sec = PostingAccountSecret.objects.create(
            account=acc,
            encrypted_data=b"some_encrypted_data",
            field_hash="hash"
        )
        self.assertEqual(sec.account, acc)

class TestTweetList(TestCase):
    def test_create_tweet_list(self):
        tlist = TweetList.objects.create(name="My List")
        entry = TweetEntry.objects.create(list=tlist, text="Hello world")
        self.assertEqual(entry.list, tlist)

class TestSchedule(TestCase):
    def test_create_schedule(self):
        acc = PostingAccount.objects.create(name="Test Account")
        tlist = TweetList.objects.create(name="Test List")

        schedule = Schedule.objects.create(
            schedule_type=Schedule.ScheduleType.ONE_TIME,
            timezone_name="UTC",
            start_datetime=timezone.now(),
            content_mode=Schedule.ContentMode.FIXED_NEW,
        )
        ScheduleTargetAccount.objects.create(schedule=schedule, account=acc)
        ScheduleSourceList.objects.create(schedule=schedule, tweet_list=tlist)

        with self.assertRaises(IntegrityError):
            ScheduleTargetAccount.objects.create(schedule=schedule, account=acc)

class TestExecution(TestCase):
    def test_create_occurrence(self):
        schedule = Schedule.objects.create(
            schedule_type=Schedule.ScheduleType.ONE_TIME,
            timezone_name="UTC",
            start_datetime=timezone.now(),
            content_mode=Schedule.ContentMode.FIXED_NEW
        )
        occ = Occurrence.objects.create(
            schedule=schedule,
            due_at=timezone.now(),
            display_timezone="UTC",
            schedule_version=1
        )
        acc = PostingAccount.objects.create(name="Test")
        OccurrenceAttempt.objects.create(
            occurrence=occ,
            target_account=acc,
            automatic_attempt_seq=1,
        )

        with self.assertRaises(IntegrityError):
            OccurrenceAttempt.objects.create(
                occurrence=occ,
                target_account=acc,
                automatic_attempt_seq=1
            )
