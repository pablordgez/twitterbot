from django.db import models
from .accounts import PostingAccount

class SMTPSettings(models.Model):
    # singleton
    host = models.CharField(max_length=255)
    port = models.PositiveIntegerField()
    username = models.CharField(max_length=255, blank=True)
    encrypted_password = models.BinaryField(blank=True, null=True)
    sender_email = models.EmailField()
    use_tls = models.BooleanField(default=True)
    use_starttls = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(
            pk=1,
            defaults={
                'host': '',
                'port': 587,
                'sender_email': '',
            }
        )
        return obj

class NotificationRecipient(models.Model):
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

class NotificationAccountState(models.Model):
    account = models.OneToOneField(PostingAccount, on_delete=models.CASCADE, related_name='notification_state')
    last_success_at = models.DateTimeField(blank=True, null=True)
    first_failure_notified = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
