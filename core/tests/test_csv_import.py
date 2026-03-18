from django.urls import reverse
from django.test import TestCase
from core.models.tweets import TweetList, TweetEntry
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

class CSVImportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin_user = User.objects.create_superuser(username="admin", password="password")
        self.tweet_list = TweetList.objects.create(name="Test List")
        self.client.force_login(self.admin_user)

    def test_csv_import_text(self):
        csv_content = "tweet 1\n\"tweet 2\nmultiline\"\ntweet 3"

        url = reverse("core:csv_import", kwargs={'list_pk': self.tweet_list.pk})
        response = self.client.post(url, {
            "target_list": self.tweet_list.pk,
            "import_mode": "paste",
            "csv_text": csv_content
        })

        self.assertEqual(response.status_code, 200) # It renders the result template
        self.assertEqual(TweetEntry.objects.filter(list=self.tweet_list).count(), 3)

    def test_csv_import_file(self):
        csv_content = b"tweet file 1\ntweet file 2\n"
        csv_file = SimpleUploadedFile("test.csv", csv_content, content_type="text/csv")

        url = reverse("core:csv_import_general")
        response = self.client.post(url, {
            "target_list": self.tweet_list.pk,
            "import_mode": "file",
            "csv_file": csv_file
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(TweetEntry.objects.filter(list=self.tweet_list).count(), 2)

    def test_csv_import_too_long(self):
        long_tweet = "A" * 300
        csv_content = f"valid\n{long_tweet}\nanother valid"

        url = reverse("core:csv_import", kwargs={'list_pk': self.tweet_list.pk})
        response = self.client.post(url, {
            "target_list": self.tweet_list.pk,
            "import_mode": "paste",
            "csv_text": csv_content
        })

        self.assertEqual(response.status_code, 200)
        # 2 valid imported, 1 rejected
        self.assertEqual(TweetEntry.objects.filter(list=self.tweet_list).count(), 2)

        self.assertEqual(response.context['imported_count'], 2)
        self.assertEqual(len(response.context['rejected']), 1)
        self.assertIn("too long", response.context['rejected'][0]['reason'])
