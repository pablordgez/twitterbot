from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from core.models.schedules import Schedule
from core.models.accounts import PostingAccount

class NFRDisplayTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='admin', password='password')
        self.client.force_login(self.user)
        self.account = PostingAccount.objects.create(name="Test Account")

    def test_schedule_list_nfr_indicators(self):
        """Verify NFR-1, NFR-2, NFR-3, NFR-4 indicators in schedule list."""
        s1 = Schedule.objects.create(
            schedule_type='one_time',
            content_mode='fixed_new',
            timezone_name='Europe/Madrid',
            start_datetime='2026-03-20 10:00:00+00:00',
            fixed_content='One-time test'
        )
        s2 = Schedule.objects.create(
            schedule_type='recurring',
            content_mode='random_from_list',
            timezone_name='UTC',
            start_datetime='2026-03-21 10:00:00+00:00',
            interval_type='day',
            interval_value=1
        )
        
        response = self.client.get(reverse('core:schedule_list'))
        self.assertEqual(response.status_code, 200)
        
        # NFR-1: One-time vs Recurring badges
        self.assertContains(response, 'One-Time')
        self.assertContains(response, 'Recurring')
        
        # NFR-2: Timezone indicator
        self.assertContains(response, 'Europe/Madrid')
        self.assertContains(response, 'UTC')
        
        # NFR-4: Fixed vs Random badges
        self.assertContains(response, 'Fixed (New)')
        self.assertContains(response, 'Random (From List)')

    def test_account_detail_nfr_test_post(self):
        """Verify NFR-6: Test post action clearly communicates 'test' text."""
        # Setup account secrets to show the test post section
        from core.models.accounts import PostingAccountSecret
        PostingAccountSecret.objects.create(
            account=self.account, 
            encrypted_data=b"dummy",
            field_hash="dummy_hash"
        )
        
        response = self.client.get(reverse('core:account_detail', args=[self.account.pk]))
        self.assertEqual(response.status_code, 200)
        
        # NFR-6: Communication of 'test' text
        self.assertContains(response, "REAL POST to X/Twitter with the exact text: test")
        self.assertContains(response, "This will post <code>test</code> to your account immediately.")

    def test_upcoming_nfr_indicators(self):
        """Verify badges in upcoming occurrences view."""
        from core.models.execution import Occurrence
        s = Schedule.objects.create(
            schedule_type='one_time',
            content_mode='fixed_new',
            timezone_name='UTC',
            start_datetime='2026-03-20 10:00:00+00:00',
            fixed_content='Upcoming test'
        )
        # Assuming materializer or manual creation
        Occurrence.objects.create(
            schedule=s,
            due_at='2026-03-20 10:00:00+00:00',
            display_timezone='UTC',
            status='pending',
            schedule_version=1
        )
        
        response = self.client.get(reverse('core:upcoming_list'))
        self.assertEqual(response.status_code, 200)
        
        # Verify consistent badges
        self.assertContains(response, 'One-Time')
        self.assertContains(response, 'Fixed (New)')
        self.assertContains(response, 'UTC')
