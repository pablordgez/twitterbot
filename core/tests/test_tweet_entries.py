from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import ValidationError
from core.models.tweets import TweetList, TweetEntry
from core.services.tweet_validation import validate_tweet_length

class TweetEntryTests(TestCase):
    def setUp(self):
        self.tweet_list = TweetList.objects.create(name="Test List")

    def test_validation_service(self):
        # Valid length
        self.assertTrue(validate_tweet_length("A" * 100))

        # Too short
        with self.assertRaises(ValidationError) as cm:
            validate_tweet_length("")
        self.assertIn("too short", str(cm.exception))

        # Too long (default 280)
        with self.assertRaises(ValidationError) as cm:
            validate_tweet_length("A" * 281)
        self.assertIn("too long", str(cm.exception))

    def test_duplicate_warning_logic(self):
        from core.forms.tweet_entries import TweetEntryForm

        # Create an entry first
        TweetEntry.objects.create(list=self.tweet_list, text="Original")

        # Try to add same text to same list
        form = TweetEntryForm(data={'text': 'Original'})
        form.tweet_list = self.tweet_list
        self.assertTrue(form.is_valid())
        self.assertTrue(getattr(form, 'is_duplicate', False))

        # Try with different text
        form = TweetEntryForm(data={'text': 'New Text'})
        form.tweet_list = self.tweet_list
        self.assertTrue(form.is_valid())
        self.assertFalse(getattr(form, 'is_duplicate', False))

    def test_tweet_entry_crud(self):
        # Create
        entry = TweetEntry.objects.create(list=self.tweet_list, text="Test tweet")
        self.assertEqual(TweetEntry.objects.count(), 1)

        # Update
        entry.text = "Updated tweet"
        entry.save()
        self.assertEqual(TweetEntry.objects.get(id=entry.id).text, "Updated tweet")

        # Delete
        entry.delete()
        self.assertEqual(TweetEntry.objects.count(), 0)

    def test_special_characters(self):
        text = "Check this out! 🚀 https://example.com #testing"
        entry = TweetEntry.objects.create(list=self.tweet_list, text=text)
        self.assertEqual(TweetEntry.objects.get(id=entry.id).text, text)

    def test_views_auth(self):
        # Setup admin
        from django.contrib.auth.models import User
        user = User.objects.create_superuser('admin', 'admin@example.com', 'pass')
        self.client.force_login(user)

        # List detail
        response = self.client.get(reverse('core:tweet_list_detail', kwargs={'pk': self.tweet_list.pk}))
        self.assertEqual(response.status_code, 200)

    def test_htmx_create_and_delete(self):
        from django.contrib.auth.models import User
        user = User.objects.create_superuser('admin', 'admin@example.com', 'pass')
        self.client.force_login(user)

        # Create via HTMX
        url = reverse('core:tweet_entry_create', kwargs={'list_pk': self.tweet_list.pk})
        response = self.client.post(url, {'text': 'HTMX Entry'}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'HTMX Entry')
        self.assertEqual(TweetEntry.objects.filter(text='HTMX Entry').count(), 1)

        entry = TweetEntry.objects.get(text='HTMX Entry')

        # Delete via HTMX
        delete_url = reverse('core:tweet_entry_delete', kwargs={'pk': entry.pk})
        response = self.client.post(delete_url, {}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "")
        self.assertEqual(TweetEntry.objects.filter(text='HTMX Entry').count(), 0)
