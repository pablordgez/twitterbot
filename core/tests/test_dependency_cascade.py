"""
Tests for T-018: Dependency Cascade on Delete.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models.accounts import PostingAccount
from core.models.execution import Occurrence
from core.models.history import HistoryEvent
from core.models.schedules import Schedule, ScheduleSourceList, ScheduleTargetAccount
from core.models.tweets import TweetList
from core.services.dependency_cascade import (
    cascade_cancel,
    check_account_dependencies,
    check_list_dependencies,
)


# ===================================================================
# Service-level tests
# ===================================================================


class CheckAccountDependenciesTests(TestCase):
    def setUp(self):
        self.account = PostingAccount.objects.create(name='Acct', is_active=True)

    def test_returns_active_schedules_for_account(self):
        schedule = Schedule.objects.create(
            schedule_type='recurring', timezone_name='UTC',
            start_datetime=timezone.now(), content_mode='fixed_new',
            fixed_content='x', status='active',
        )
        ScheduleTargetAccount.objects.create(schedule=schedule, account=self.account)

        result = check_account_dependencies(self.account)
        self.assertEqual(result, [schedule])

    def test_excludes_canceled_schedules(self):
        schedule = Schedule.objects.create(
            schedule_type='one_time', timezone_name='UTC',
            start_datetime=timezone.now(), content_mode='fixed_new',
            fixed_content='x', status='canceled',
        )
        ScheduleTargetAccount.objects.create(schedule=schedule, account=self.account)

        result = check_account_dependencies(self.account)
        self.assertEqual(result, [])

    def test_returns_empty_when_no_schedules(self):
        self.assertEqual(check_account_dependencies(self.account), [])


class CheckListDependenciesTests(TestCase):
    def setUp(self):
        self.tweet_list = TweetList.objects.create(name='List')

    def test_returns_active_schedules_for_list(self):
        schedule = Schedule.objects.create(
            schedule_type='recurring', timezone_name='UTC',
            start_datetime=timezone.now(), content_mode='random_from_list',
            status='active',
        )
        ScheduleSourceList.objects.create(schedule=schedule, tweet_list=self.tweet_list)

        result = check_list_dependencies(self.tweet_list)
        self.assertEqual(result, [schedule])

    def test_excludes_canceled_schedules(self):
        schedule = Schedule.objects.create(
            schedule_type='recurring', timezone_name='UTC',
            start_datetime=timezone.now(), content_mode='random_from_list',
            status='canceled',
        )
        ScheduleSourceList.objects.create(schedule=schedule, tweet_list=self.tweet_list)

        result = check_list_dependencies(self.tweet_list)
        self.assertEqual(result, [])


class CascadeCancelTests(TestCase):
    def setUp(self):
        self.schedule = Schedule.objects.create(
            schedule_type='recurring', timezone_name='UTC',
            start_datetime=timezone.now(), content_mode='fixed_new',
            fixed_content='x', status='active',
        )
        self.pending_occ = Occurrence.objects.create(
            schedule=self.schedule,
            due_at=timezone.now() + timedelta(days=1),
            display_timezone='UTC', schedule_version=1,
            status=Occurrence.Status.PENDING,
        )
        self.completed_occ = Occurrence.objects.create(
            schedule=self.schedule,
            due_at=timezone.now() - timedelta(days=1),
            display_timezone='UTC', schedule_version=1,
            status=Occurrence.Status.COMPLETED,
        )

    def test_sets_schedule_status_canceled(self):
        cascade_cancel([self.schedule], 'account_deleted')
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status, 'canceled')

    def test_cancels_pending_occurrences_with_reason(self):
        cascade_cancel([self.schedule], 'account_deleted')
        self.pending_occ.refresh_from_db()
        self.assertEqual(self.pending_occ.status, Occurrence.Status.CANCELED)
        self.assertEqual(self.pending_occ.cancel_reason, 'account_deleted')

    def test_preserves_completed_occurrences(self):
        cascade_cancel([self.schedule], 'account_deleted')
        self.completed_occ.refresh_from_db()
        self.assertEqual(self.completed_occ.status, Occurrence.Status.COMPLETED)

    def test_logs_dependency_cascade_cancel(self):
        cascade_cancel([self.schedule], 'list_deleted')
        event = HistoryEvent.objects.filter(
            event_type='DEPENDENCY_CASCADE_CANCEL',
            schedule=self.schedule,
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.detail['reason'], 'list_deleted')

    def test_handles_multiple_schedules(self):
        schedule2 = Schedule.objects.create(
            schedule_type='one_time', timezone_name='UTC',
            start_datetime=timezone.now(), content_mode='fixed_new',
            fixed_content='y', status='active',
        )
        Occurrence.objects.create(
            schedule=schedule2, due_at=timezone.now() + timedelta(days=2),
            display_timezone='UTC', schedule_version=1,
            status=Occurrence.Status.PENDING,
        )
        cascade_cancel([self.schedule, schedule2], 'account_deleted')

        self.schedule.refresh_from_db()
        schedule2.refresh_from_db()
        self.assertEqual(self.schedule.status, 'canceled')
        self.assertEqual(schedule2.status, 'canceled')
        self.assertEqual(
            HistoryEvent.objects.filter(event_type='DEPENDENCY_CASCADE_CANCEL').count(), 2,
        )

    def test_only_affects_target_schedule_occurrences(self):
        other_schedule = Schedule.objects.create(
            schedule_type='one_time', timezone_name='UTC',
            start_datetime=timezone.now(), content_mode='fixed_new',
            fixed_content='z', status='active',
        )
        other_occ = Occurrence.objects.create(
            schedule=other_schedule, due_at=timezone.now() + timedelta(days=1),
            display_timezone='UTC', schedule_version=1,
            status=Occurrence.Status.PENDING,
        )

        cascade_cancel([self.schedule], 'account_deleted')

        other_occ.refresh_from_db()
        self.assertEqual(other_occ.status, Occurrence.Status.PENDING)


# ===================================================================
# Integration tests — Account delete view
# ===================================================================


class AccountDeleteCascadeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='admin', password='testpass123')
        self.client = Client()
        self.client.force_login(self.user)

        self.account = PostingAccount.objects.create(name='Acct', is_active=True)
        self.schedule = Schedule.objects.create(
            schedule_type='recurring', timezone_name='UTC',
            start_datetime=timezone.now(), content_mode='fixed_new',
            fixed_content='x', status='active',
        )
        ScheduleTargetAccount.objects.create(schedule=self.schedule, account=self.account)
        self.pending_occ = Occurrence.objects.create(
            schedule=self.schedule,
            due_at=timezone.now() + timedelta(days=1),
            display_timezone='UTC', schedule_version=1,
            status=Occurrence.Status.PENDING,
        )

    def test_delete_page_shows_dependency_warning(self):
        response = self.client.get(
            reverse('core:account_delete', kwargs={'pk': self.account.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dependency Impact')

    def test_confirm_delete_cascades(self):
        self.client.post(
            reverse('core:account_delete', kwargs={'pk': self.account.pk}),
        )
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status, 'canceled')

        self.pending_occ.refresh_from_db()
        self.assertEqual(self.pending_occ.status, Occurrence.Status.CANCELED)
        self.assertEqual(self.pending_occ.cancel_reason, 'account_deleted')

    def test_confirm_delete_logs_audit_events(self):
        self.client.post(
            reverse('core:account_delete', kwargs={'pk': self.account.pk}),
        )
        self.assertTrue(
            HistoryEvent.objects.filter(event_type='DEPENDENCY_CASCADE_CANCEL').exists(),
        )
        self.assertTrue(
            HistoryEvent.objects.filter(event_type='DEPENDENCY_DELETE_CONFIRMED').exists(),
        )

    def test_delete_without_dependencies_succeeds(self):
        account2 = PostingAccount.objects.create(name='NoDepAcct', is_active=True)
        response = self.client.post(
            reverse('core:account_delete', kwargs={'pk': account2.pk}),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PostingAccount.objects.filter(pk=account2.pk).exists())


# ===================================================================
# Integration tests — Tweet list delete view
# ===================================================================


class TweetListDeleteCascadeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='admin', password='testpass123')
        self.client = Client()
        self.client.force_login(self.user)

        self.tweet_list = TweetList.objects.create(name='List')
        self.schedule = Schedule.objects.create(
            schedule_type='recurring', timezone_name='UTC',
            start_datetime=timezone.now(), content_mode='random_from_list',
            status='active',
        )
        ScheduleSourceList.objects.create(schedule=self.schedule, tweet_list=self.tweet_list)
        self.pending_occ = Occurrence.objects.create(
            schedule=self.schedule,
            due_at=timezone.now() + timedelta(days=1),
            display_timezone='UTC', schedule_version=1,
            status=Occurrence.Status.PENDING,
        )

    def test_delete_page_shows_dependency_warning(self):
        response = self.client.get(
            reverse('core:tweet_list_delete', kwargs={'pk': self.tweet_list.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dependency Impact')

    def test_confirm_delete_cascades(self):
        self.client.post(
            reverse('core:tweet_list_delete', kwargs={'pk': self.tweet_list.pk}),
        )
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status, 'canceled')

        self.pending_occ.refresh_from_db()
        self.assertEqual(self.pending_occ.status, Occurrence.Status.CANCELED)
        self.assertEqual(self.pending_occ.cancel_reason, 'list_deleted')

    def test_confirm_delete_logs_audit_events(self):
        self.client.post(
            reverse('core:tweet_list_delete', kwargs={'pk': self.tweet_list.pk}),
        )
        self.assertTrue(
            HistoryEvent.objects.filter(event_type='DEPENDENCY_CASCADE_CANCEL').exists(),
        )
        self.assertTrue(
            HistoryEvent.objects.filter(event_type='DEPENDENCY_DELETE_CONFIRMED').exists(),
        )
