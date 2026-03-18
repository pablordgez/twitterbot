from django.test import TestCase
from django.core import mail
from django.utils import timezone
from unittest.mock import patch

from core.models.accounts import PostingAccount
from core.models.notifications import SMTPSettings, NotificationRecipient, NotificationAccountState
from core.models.history import HistoryEvent
from core.models.execution import Occurrence, OccurrenceAttempt
from core.models.schedules import Schedule
from core.services.notification_engine import handle_posting_result

class NotificationEngineTests(TestCase):
    def setUp(self):
        self.smtp_settings = SMTPSettings.objects.create(
            host='smtp.example.com',
            port=587,
            sender_email='bot@example.com',
            use_tls=False,
            use_starttls=True
        )

        self.recipient = NotificationRecipient.objects.create(email='admin@example.com')

        self.schedule = Schedule.objects.create(
            schedule_type=Schedule.ScheduleType.ONE_TIME,
            start_datetime=timezone.now(),
            content_mode=Schedule.ContentMode.FIXED_NEW,
            timezone_name="UTC"
        )

        self.occurrence = Occurrence.objects.create(schedule=self.schedule, due_at=timezone.now(), schedule_version=1)

        self.account_none = PostingAccount.objects.create(
            name='Acct None',
            notification_mode=PostingAccount.NotificationMode.NONE
        )

        self.account_first = PostingAccount.objects.create(
            name='Acct First',
            notification_mode=PostingAccount.NotificationMode.FIRST_FAILURE
        )

        self.account_every = PostingAccount.objects.create(
            name='Acct Every',
            notification_mode=PostingAccount.NotificationMode.EVERY_FAILURE
        )

    def create_attempt(self, account, error_detail="Mock error"):
        return OccurrenceAttempt.objects.create(
            occurrence=self.occurrence,
            target_account=account,
            post_result=OccurrenceAttempt.PostResult.FAILED,
            error_detail=error_detail
        )

    def test_mode_none_skips(self):
        attempt = self.create_attempt(self.account_none)
        handle_posting_result(self.account_none, False, attempt)
        self.assertEqual(len(mail.outbox), 0)

    def test_mode_every_sends_always(self):
        attempt = self.create_attempt(self.account_every)

        handle_posting_result(self.account_every, False, attempt)
        self.assertEqual(len(mail.outbox), 1)

        handle_posting_result(self.account_every, False, attempt)
        self.assertEqual(len(mail.outbox), 2)

    def test_mode_first_sends_once_then_suppresses(self):
        attempt = self.create_attempt(self.account_first)

        # First failure -> sends
        handle_posting_result(self.account_first, False, attempt)
        self.assertEqual(len(mail.outbox), 1)
        state = NotificationAccountState.objects.get(account=self.account_first)
        self.assertTrue(state.first_failure_notified)

        # Second failure -> suppressed
        handle_posting_result(self.account_first, False, attempt)
        self.assertEqual(len(mail.outbox), 1)  # Still 1

    def test_success_resets_state(self):
        attempt = self.create_attempt(self.account_first)

        # First failure -> sends
        handle_posting_result(self.account_first, False, attempt)
        self.assertEqual(len(mail.outbox), 1)

        # Success -> resets
        handle_posting_result(self.account_first, True, attempt)
        state = NotificationAccountState.objects.get(account=self.account_first)
        self.assertFalse(state.first_failure_notified)
        self.assertIsNotNone(state.last_success_at)

        # Next failure -> sends again
        handle_posting_result(self.account_first, False, attempt)
        self.assertEqual(len(mail.outbox), 2)

    @patch("django.core.mail.EmailMessage.send")
    def test_smtp_failure_isolated(self, mock_send):
        attempt = self.create_attempt(self.account_every)
        mock_send.side_effect = Exception("SMTP Server Down")

        # Should not raise exception
        handle_posting_result(self.account_every, False, attempt)

        self.assertEqual(len(mail.outbox), 0)
        event = HistoryEvent.objects.filter(event_type='NOTIFICATION_FAILED').first()
        self.assertIsNotNone(event)
        self.assertIn("SMTP Server Down", event.content_summary)
        self.assertEqual(event.result_status, 'failed')

    def test_per_account_independence(self):
        account_first_2 = PostingAccount.objects.create(
            name='Acct First 2',
            notification_mode=PostingAccount.NotificationMode.FIRST_FAILURE
        )

        attempt1 = self.create_attempt(self.account_first)
        attempt2 = self.create_attempt(account_first_2)

        # Account 1 fails -> sends
        handle_posting_result(self.account_first, False, attempt1)
        self.assertEqual(len(mail.outbox), 1)

        # Account 2 fails -> sends (independent)
        handle_posting_result(account_first_2, False, attempt2)
        self.assertEqual(len(mail.outbox), 2)

        # Account 1 fails again -> suppressed
        handle_posting_result(self.account_first, False, attempt1)
        self.assertEqual(len(mail.outbox), 2)

    def test_email_body_redaction_and_content(self):
        attempt = self.create_attempt(self.account_every, error_detail="Redacted error detail")

        handle_posting_result(self.account_every, False, attempt)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        self.assertEqual(email.subject, f"[TwitterBot] Posting Failure: {self.account_every.name}")
        self.assertIn(self.account_every.name, email.body)
        self.assertIn("Redacted error detail", email.body)
        self.assertNotIn("Unknown error", email.body)
        self.assertIn("Schedule", email.body)

    def test_no_settings_skips_gracefully(self):
        # Delete settings to simulate missing
        SMTPSettings.objects.all().delete()

        attempt = self.create_attempt(self.account_every)
        handle_posting_result(self.account_every, False, attempt)

        self.assertEqual(len(mail.outbox), 0)

    def test_no_recipients_skips_gracefully(self):
        NotificationRecipient.objects.all().delete()

        attempt = self.create_attempt(self.account_every)
        handle_posting_result(self.account_every, False, attempt)

        self.assertEqual(len(mail.outbox), 0)

    @patch("django.core.mail.EmailMessage.send")
    def test_notification_failure_redacts_secret_like_exception_text(self, mock_send):
        attempt = self.create_attempt(self.account_every)
        mock_send.side_effect = Exception(
            "SMTP failure authorization=Bearer super-secret-token token=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )

        handle_posting_result(self.account_every, False, attempt)

        event = HistoryEvent.objects.filter(event_type='NOTIFICATION_FAILED').first()
        self.assertIsNotNone(event)
        self.assertNotIn('super-secret-token', event.detail['error'])
        self.assertNotIn('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', event.detail['error'])
        self.assertIn('***REDACTED***', event.detail['error'])
