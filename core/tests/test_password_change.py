from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from core.models.history import HistoryEvent

class PasswordChangeTests(TestCase):
    def setUp(self):
        self.username = 'admin'
        self.old_password = 'old_password_123'
        self.new_password = 'new_password_456'
        self.user = User.objects.create_superuser(self.username, '', self.old_password)
        self.client.force_login(self.user)

    def test_password_change_view_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('core:password_change'))
        self.assertRedirects(response, f"{reverse('core:login')}?next={reverse('core:password_change')}")

    def test_password_change_success(self):
        response = self.client.post(reverse('core:password_change'), {
            'old_password': self.old_password,
            'new_password1': self.new_password,
            'new_password2': self.new_password,
        }, follow=True)

        self.assertRedirects(response, reverse('core:dashboard'))
        self.assertContains(response, 'Your password has been successfully changed.')

        # Verify password actually changed
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertFalse(self.user.check_password(self.old_password))

        # Verify history log
        self.assertTrue(HistoryEvent.objects.filter(
            event_type='AUTH_PASSWORD_CHANGED',
            detail__username=self.username
        ).exists())

    def test_password_change_invalid_old_password(self):
        response = self.client.post(reverse('core:password_change'), {
            'old_password': 'wrong_old_password',
            'new_password1': self.new_password,
            'new_password2': self.new_password,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your old password was entered incorrectly. Please enter it again.')

        # Verify password NOT changed
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def test_password_change_mismatch_new_passwords(self):
        response = self.client.post(reverse('core:password_change'), {
            'old_password': self.old_password,
            'new_password1': self.new_password,
            'new_password2': 'different_password',
        })

        self.assertEqual(response.status_code, 200)
        # Django's PasswordChangeForm raises __all__ error for mismatch
        self.assertContains(response, 'The two password fields didn’t match.')

        # Verify password NOT changed
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def test_session_remains_active_after_password_change(self):
        # By default, changing password invalidates all sessions.
        # update_session_auth_hash should prevent the current session from being invalidated.
        response = self.client.post(reverse('core:password_change'), {
            'old_password': self.old_password,
            'new_password1': self.new_password,
            'new_password2': self.new_password,
        })

        # Check if user is still logged in
        self.assertTrue('_auth_user_id' in self.client.session)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)
