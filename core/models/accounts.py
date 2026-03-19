from django.db import models

class PostingAccount(models.Model):
    class AuthMode(models.TextChoices):
        REQUEST = 'request', 'Request Secrets'
        BROWSER = 'browser', 'Browser Login'

    class NotificationMode(models.TextChoices):
        NONE = 'none', 'None'
        FIRST_FAILURE = 'first_failure', 'First Failure'
        EVERY_FAILURE = 'every_failure', 'Every Failure'

    name = models.CharField(max_length=255)
    auth_mode = models.CharField(
        max_length=20,
        choices=AuthMode.choices,
        default=AuthMode.REQUEST,
    )
    is_active = models.BooleanField(default=True)
    notification_mode = models.CharField(
        max_length=20,
        choices=NotificationMode.choices,
        default=NotificationMode.FIRST_FAILURE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class PostingAccountSecret(models.Model):
    account = models.OneToOneField(PostingAccount, on_delete=models.CASCADE, related_name='secret')
    encrypted_data = models.BinaryField()
    field_hash = models.CharField(max_length=255)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Secret for {self.account.name}"


class PostingAccountBrowserCredential(models.Model):
    account = models.OneToOneField(
        PostingAccount,
        on_delete=models.CASCADE,
        related_name='browser_credential',
    )
    encrypted_username = models.BinaryField()
    encrypted_password = models.BinaryField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Browser credential for {self.account.name}"
