"""
Tests for T-012: Schedule Create/Edit Forms and Views.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from core.models.accounts import PostingAccount
from core.models.schedules import Schedule, ScheduleTargetAccount, ScheduleSourceList
from core.models.tweets import TweetList
from core.forms.schedules import ScheduleForm


class ScheduleFormTestCase(TestCase):
    """Shared setup for all schedule form tests."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin', password='testpass123',
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.account = PostingAccount.objects.create(name='TestAccount', is_active=True)
        self.tweet_list = TweetList.objects.create(name='TestList')

    def _base_form_data(self, **overrides):
        """Return minimal valid form data for a one-time schedule."""
        future = (timezone.now() + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')
        data = {
            'schedule_type': 'one_time',
            'start_datetime': future,
            'timezone_mode': 'system',
            'timezone_other': '',
            'content_mode': 'fixed_new',
            'fixed_content': 'Hello world',
            'target_accounts': [self.account.pk],
            'source_lists': [],
            'interval_type': '',
            'interval_value': '',
            'random_resolution_mode': '',
            'reuse_enabled': '',
            'exhaustion_behavior': '',
        }
        data.update(overrides)
        return data


# ===================================================================
# Form rendering
# ===================================================================


class ScheduleFormRenderingTests(ScheduleFormTestCase):
    def test_form_renders_all_fields(self):
        """Form should contain all expected fields."""
        form = ScheduleForm()
        expected_fields = [
            'schedule_type', 'start_datetime', 'timezone_mode',
            'timezone_other', 'target_accounts', 'source_lists',
            'content_mode', 'fixed_content', 'interval_type',
            'interval_value', 'random_resolution_mode',
            'reuse_enabled', 'exhaustion_behavior',
        ]
        for field_name in expected_fields:
            self.assertIn(field_name, form.fields, f"Missing field: {field_name}")

    def test_system_timezone_shown_in_choices(self):
        """Timezone mode should show the actual system TZ name."""
        form = ScheduleForm()
        choices = dict(form.fields['timezone_mode'].choices)
        self.assertIn(settings.TIME_ZONE, choices.get('system', ''))

    def test_create_page_renders(self):
        """GET on the create page should return 200."""
        response = self.client.get(reverse('core:schedule_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'New Schedule')


# ===================================================================
# One-time schedule creation
# ===================================================================


class OneTimeScheduleCreateTests(ScheduleFormTestCase):
    def test_create_one_time_schedule(self):
        """A valid one-time schedule POST saves the correct model graph."""
        data = self._base_form_data()
        response = self.client.post(reverse('core:schedule_create'), data)
        self.assertEqual(response.status_code, 302)

        schedule = Schedule.objects.first()
        self.assertIsNotNone(schedule)
        self.assertEqual(schedule.schedule_type, 'one_time')
        self.assertEqual(schedule.content_mode, 'fixed_new')
        self.assertEqual(schedule.fixed_content, 'Hello world')
        self.assertEqual(schedule.timezone_name, settings.TIME_ZONE)

        # Join records
        self.assertEqual(
            ScheduleTargetAccount.objects.filter(schedule=schedule).count(), 1,
        )

    def test_create_with_utc_timezone(self):
        """Selecting timezone_mode=utc should resolve timezone_name to 'UTC'."""
        data = self._base_form_data(timezone_mode='utc')
        self.client.post(reverse('core:schedule_create'), data)

        schedule = Schedule.objects.first()
        self.assertEqual(schedule.timezone_name, 'UTC')

    def test_create_with_other_timezone(self):
        """Selecting timezone_mode=other + a valid IANA zone should work."""
        data = self._base_form_data(
            timezone_mode='other', timezone_other='US/Eastern',
        )
        self.client.post(reverse('core:schedule_create'), data)

        schedule = Schedule.objects.first()
        self.assertEqual(schedule.timezone_name, 'US/Eastern')

    def test_create_with_empty_other_timezone_fails(self):
        """timezone_mode=other without a value should fail validation."""
        data = self._base_form_data(
            timezone_mode='other', timezone_other='',
        )
        response = self.client.post(reverse('core:schedule_create'), data)
        self.assertEqual(response.status_code, 200)  # re-renders form
        self.assertEqual(Schedule.objects.count(), 0)


# ===================================================================
# Recurring schedule creation
# ===================================================================


class RecurringScheduleCreateTests(ScheduleFormTestCase):
    def test_create_recurring_schedule(self):
        """A valid recurring schedule POST saves all recurring fields + join records."""
        data = self._base_form_data(
            schedule_type='recurring',
            interval_type='hours',
            interval_value='6',
        )
        response = self.client.post(reverse('core:schedule_create'), data)
        self.assertEqual(response.status_code, 302)

        schedule = Schedule.objects.first()
        self.assertIsNotNone(schedule)
        self.assertEqual(schedule.schedule_type, 'recurring')
        self.assertEqual(schedule.interval_type, 'hours')
        self.assertEqual(schedule.interval_value, 6)

    def test_recurring_with_list_content(self):
        """Recurring + random_from_list requires a source list."""
        data = self._base_form_data(
            schedule_type='recurring',
            content_mode='random_from_list',
            fixed_content='',
            interval_type='days',
            interval_value='1',
            source_lists=[self.tweet_list.pk],
        )
        response = self.client.post(reverse('core:schedule_create'), data)
        self.assertEqual(response.status_code, 302)

        schedule = Schedule.objects.first()
        self.assertEqual(schedule.content_mode, 'random_from_list')
        self.assertEqual(
            ScheduleSourceList.objects.filter(schedule=schedule).count(), 1,
        )


# ===================================================================
# Validation errors
# ===================================================================


class ScheduleValidationTests(ScheduleFormTestCase):
    def test_no_accounts_fails(self):
        """Schedule without target accounts should fail validation."""
        data = self._base_form_data(target_accounts=[])
        response = self.client.post(reverse('core:schedule_create'), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Schedule.objects.count(), 0)

    def test_fixed_new_without_content_fails(self):
        """Fixed New mode without text should fail."""
        data = self._base_form_data(fixed_content='')
        response = self.client.post(reverse('core:schedule_create'), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Schedule.objects.count(), 0)

    def test_recurring_without_interval_fails(self):
        """Recurring schedule without interval should fail."""
        data = self._base_form_data(
            schedule_type='recurring',
            interval_type='',
            interval_value='',
        )
        response = self.client.post(reverse('core:schedule_create'), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Schedule.objects.count(), 0)


# ===================================================================
# Schedule edit / version increment
# ===================================================================


class ScheduleEditTests(ScheduleFormTestCase):
    def test_edit_increments_version(self):
        """Editing a schedule should increment its version."""
        # Create the schedule first
        data = self._base_form_data()
        self.client.post(reverse('core:schedule_create'), data)
        schedule = Schedule.objects.first()
        self.assertEqual(schedule.version, 1)

        # Edit it
        future = (timezone.now() + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')
        edit_data = self._base_form_data(
            start_datetime=future,
            fixed_content='Updated content',
        )
        response = self.client.post(
            reverse('core:schedule_update', kwargs={'pk': schedule.pk}),
            edit_data,
        )
        self.assertEqual(response.status_code, 302)

        schedule.refresh_from_db()
        self.assertEqual(schedule.version, 2)
        self.assertEqual(schedule.fixed_content, 'Updated content')

    def test_edit_page_renders(self):
        """GET on the edit page should return 200."""
        data = self._base_form_data()
        self.client.post(reverse('core:schedule_create'), data)
        schedule = Schedule.objects.first()

        response = self.client.get(
            reverse('core:schedule_update', kwargs={'pk': schedule.pk}),
        )
        self.assertEqual(response.status_code, 200)


# ===================================================================
# Schedule cancel
# ===================================================================


class ScheduleCancelTests(ScheduleFormTestCase):
    def test_cancel_sets_status(self):
        """POSTing to cancel should set schedule status to 'canceled'."""
        data = self._base_form_data()
        self.client.post(reverse('core:schedule_create'), data)
        schedule = Schedule.objects.first()

        response = self.client.post(
            reverse('core:schedule_cancel', kwargs={'pk': schedule.pk}),
        )
        self.assertEqual(response.status_code, 302)

        schedule.refresh_from_db()
        self.assertEqual(schedule.status, 'canceled')


# ===================================================================
# Schedule list and detail views
# ===================================================================


class ScheduleViewTests(ScheduleFormTestCase):
    def test_list_view(self):
        """Schedule list page should render."""
        response = self.client.get(reverse('core:schedule_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Schedules')

    def test_detail_view(self):
        """Schedule detail page should show schedule info."""
        data = self._base_form_data()
        self.client.post(reverse('core:schedule_create'), data)
        schedule = Schedule.objects.first()

        response = self.client.get(
            reverse('core:schedule_detail', kwargs={'pk': schedule.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Schedule Details')

    def test_detail_shows_dst_indicator_for_recurring_non_utc(self):
        """Detail view for recurring non-UTC should show DST indicator."""
        data = self._base_form_data(
            schedule_type='recurring',
            timezone_mode='other',
            timezone_other='US/Eastern',
            interval_type='days',
            interval_value='1',
        )
        self.client.post(reverse('core:schedule_create'), data)
        schedule = Schedule.objects.first()

        response = self.client.get(
            reverse('core:schedule_detail', kwargs={'pk': schedule.pk}),
        )
        self.assertContains(response, 'Automatic DST adjustment')
        self.assertContains(response, 'US/Eastern')


# ===================================================================
# HTMX partial views
# ===================================================================


class HTMXPartialViewTests(ScheduleFormTestCase):
    def test_recurring_fields_partial_shows(self):
        """Requesting recurring fields partial with schedule_type=recurring should contain interval fields."""
        response = self.client.get(
            reverse('core:schedule_recurring_partial'),
            {'schedule_type': 'recurring'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Recurring Settings')

    def test_recurring_fields_partial_hidden(self):
        """Requesting recurring fields partial with schedule_type=one_time should hide fields."""
        response = self.client.get(
            reverse('core:schedule_recurring_partial'),
            {'schedule_type': 'one_time'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'display:none;')

    def test_content_mode_partial(self):
        """Content mode partial view should return 200."""
        response = self.client.get(
            reverse('core:schedule_content_mode_partial'),
            {'content_mode': 'fixed_new'},
        )
        self.assertEqual(response.status_code, 200)


# ===================================================================
# Auth required
# ===================================================================


class ScheduleAuthTests(TestCase):
    def setUp(self):
        # Need an admin user so FirstRunMiddleware doesn't redirect to /setup/
        User.objects.create_superuser(username='admin', password='testpass123')

    def test_unauthenticated_redirects(self):
        """Schedule views should redirect unauthenticated users."""
        client = Client()
        urls = [
            reverse('core:schedule_list'),
            reverse('core:schedule_create'),
        ]
        for url in urls:
            response = client.get(url)
            self.assertEqual(response.status_code, 302, f"Unprotected: {url}")
            self.assertIn('login', response.url)
