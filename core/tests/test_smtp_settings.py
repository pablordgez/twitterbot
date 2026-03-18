from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core import mail
from core.models.notifications import SMTPSettings, NotificationRecipient
from core.models.history import HistoryEvent
from core.services.encryption import get_fernet_instance, encrypt, decrypt

User = get_user_model()

class SMTPSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='admin', password='password123')
        self.client.force_login(self.user)
        self.settings = SMTPSettings.load()

    def test_view_smtp_settings_page(self):
        response = self.client.get(reverse('core:smtp_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SMTP Settings')

    def test_save_smtp_settings(self):
        data = {
            'host': 'smtp.example.com',
            'port': 587,
            'username': 'user@example.com',
            'password': 'secretpassword',
            'sender_email': 'noreply@example.com',
            'use_tls': True,
        }
        response = self.client.post(reverse('core:smtp_settings'), data)
        self.assertRedirects(response, reverse('core:smtp_settings'))
        
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.host, 'smtp.example.com')
        self.assertEqual(self.settings.port, 587)
        self.assertEqual(self.settings.username, 'user@example.com')
        self.assertEqual(self.settings.sender_email, 'noreply@example.com')
        self.assertTrue(self.settings.use_tls)
        
        # Verify password encryption
        self.assertIsNotNone(self.settings.encrypted_password)
        decrypted = decrypt(self.settings.encrypted_password)
        self.assertEqual(decrypted, 'secretpassword')

        # Verify audit log
        self.assertTrue(HistoryEvent.objects.filter(event_type='SMTP_SECRET_REPLACED').exists())

    def test_save_smtp_settings_without_changing_password(self):
        self.settings.encrypted_password = encrypt('oldpassword')
        self.settings.save()
        
        data = {
            'host': 'smtp.example.com',
            'port': 587,
            'username': 'user@example.com',
            'password': '', # Left blank
            'sender_email': 'noreply@example.com',
            'use_tls': True,
        }
        response = self.client.post(reverse('core:smtp_settings'), data)
        self.assertRedirects(response, reverse('core:smtp_settings'))
        
        self.settings.refresh_from_db()
        decrypted = decrypt(self.settings.encrypted_password)
        self.assertEqual(decrypted, 'oldpassword')
        
        # No audit log if password not changed
        self.assertFalse(HistoryEvent.objects.filter(event_type='SMTP_SECRET_REPLACED').exists())

    def test_add_recipient(self):
        response = self.client.post(reverse('core:recipient_add'), {'email': 'test@example.com'})
        self.assertRedirects(response, reverse('core:smtp_settings'))
        self.assertTrue(NotificationRecipient.objects.filter(email='test@example.com').exists())

    def test_add_invalid_recipient(self):
        response = self.client.post(reverse('core:recipient_add'), {'email': 'invalid-email'})
        self.assertRedirects(response, reverse('core:smtp_settings'))
        self.assertFalse(NotificationRecipient.objects.exists())

    def test_delete_recipient(self):
        recipient = NotificationRecipient.objects.create(email='test@example.com')
        response = self.client.post(reverse('core:recipient_delete', args=[recipient.pk]))
        self.assertRedirects(response, reverse('core:smtp_settings'))
        self.assertFalse(NotificationRecipient.objects.filter(pk=recipient.pk).exists())

    def test_test_email(self):
        self.settings.host = 'localhost'
        self.settings.port = 1025
        self.settings.sender_email = 'sender@example.com'
        self.settings.save()
        
        NotificationRecipient.objects.create(email='rcpt1@example.com')
        NotificationRecipient.objects.create(email='rcpt2@example.com')
        
        # We need to mock EmailBackend or let it use the locmem backend.
        # By default in tests, Django uses locmem backend which intercepts send_mail.
        # But our view explicitly instantiates EmailBackend.
        # Let's patch the view's backend or just mock `send`.
        
        from unittest.mock import patch
        with patch('django.core.mail.EmailMessage.send') as mock_send:
            response = self.client.post(reverse('core:smtp_test_email'))
            self.assertRedirects(response, reverse('core:smtp_settings'))
            self.assertTrue(mock_send.called)
            
            self.assertTrue(HistoryEvent.objects.filter(event_type='TEST_POST_SUCCEEDED').exists())

    def test_test_email_fails(self):
        self.settings.host = 'localhost'
        self.settings.sender_email = 'sender@example.com'
        self.settings.save()
        NotificationRecipient.objects.create(email='rcpt1@example.com')
        
        from unittest.mock import patch
        with patch('django.core.mail.EmailMessage.send', side_effect=Exception('SMTP Error')):
            response = self.client.post(reverse('core:smtp_test_email'))
            self.assertRedirects(response, reverse('core:smtp_settings'))
            self.assertTrue(HistoryEvent.objects.filter(event_type='TEST_POST_FAILED').exists())
