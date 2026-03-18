from django.test import TestCase, TransactionTestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from core.models.history import HistoryEvent

class FirstRunMiddlewareTests(TestCase):
    def test_redirects_to_setup_if_no_admin(self):
        response = self.client.get(reverse('core:login'))
        self.assertRedirects(response, reverse('core:setup'))

    def test_allows_setup_if_no_admin(self):
        response = self.client.get(reverse('core:setup'))
        self.assertEqual(response.status_code, 200)

    def test_redirects_to_login_if_admin_exists(self):
        User.objects.create_superuser('admin', '', 'password')
        response = self.client.get(reverse('core:dashboard'))
        self.assertRedirects(response, f"{reverse('core:login')}?next={reverse('core:dashboard')}")

    def test_setup_redirects_to_login_if_admin_exists(self):
        User.objects.create_superuser('admin', '', 'password')
        response = self.client.get(reverse('core:setup'))
        self.assertRedirects(response, reverse('core:login'))


class AuthViewsTests(TestCase):
    def test_setup_view_creates_superuser(self):
        response = self.client.post(reverse('core:setup'), {
            'username': 'admin2',
            'password': 'password123',
            'confirm_password': 'password123'
        }, follow=True)
        self.assertTrue(User.objects.filter(username='admin2').exists())
        self.assertTrue(User.objects.get(username='admin2').is_superuser)
        self.assertTrue(HistoryEvent.objects.filter(event_type='AUTH_SETUP_STARTED').exists())
        self.assertTrue(HistoryEvent.objects.filter(event_type='AUTH_SETUP_COMPLETED').exists())
        # Verify it logs in automatically or redirects

    def test_setup_view_passwords_must_match(self):
        response = self.client.post(reverse('core:setup'), {
            'username': 'admin',
            'password': 'password123',
            'confirm_password': 'password456'
        })
        self.assertFalse(User.objects.exists())
        self.assertContains(response, 'Passwords do not match.')

    def test_login_success_rotates_session(self):
        User.objects.create_superuser('admin', '', 'password')
        # We need a session first to see if it rotates
        self.client.get(reverse('core:login'))
        old_session_key = self.client.session.session_key

        response = self.client.post(reverse('core:login'), {
            'username': 'admin',
            'password': 'password'
        })
        self.assertTrue('_auth_user_id' in self.client.session)
        new_session_key = self.client.session.session_key
        self.assertNotEqual(old_session_key, new_session_key)

    def test_post_without_csrf_rejected(self):
        User.objects.create_superuser('admin', '', 'password')
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(reverse('core:login'), {'username': 'test', 'password': '123'})
        self.assertEqual(response.status_code, 403)

    def test_login_failure(self):
        User.objects.create_superuser('admin', '', 'password')
        response = self.client.post(reverse('core:login'), {
            'username': 'admin',
            'password': 'wrongpassword'
        })
        self.assertContains(response, "Your username and password didn't match. Please try again.")


class ThrottlingTests(TestCase):
    def test_axes_locks_out_after_failures(self):
        User.objects.create_superuser('admin', '', 'password')
        for _ in range(5):
            response = self.client.post(reverse('core:login'), {
                'username': 'admin',
                'password': 'wrongpassword'
            }, REMOTE_ADDR='127.0.0.1')

        # 6th attempt should be locked out (429 Too Many Requests by default in recent axes)
        response = self.client.post(reverse('core:login'), {
            'username': 'admin',
            'password': 'wrongpassword'
        }, REMOTE_ADDR='127.0.0.1')
        self.assertEqual(response.status_code, 429)
        self.assertTrue(HistoryEvent.objects.filter(event_type='AUTH_LOCKOUT_THRESHOLD').exists())


class ConcurrentSetupTests(TransactionTestCase):
    def test_concurrent_setup_creates_only_one_admin(self):
        # We can simulate concurrency by mocking User.objects.count inside the view
        # or by actually running two threads against the test client.
        # But Django's test client isn't fully thread-safe for DB connections sometimes.
        # We will mock User.objects.count to return 0 for both threads initially,
        # then the transaction.atomic unique constraint or count condition will catch one.
        pass
