from django.db import models
from .schedules import Schedule
from .accounts import PostingAccount
from .tweets import TweetEntry

class Occurrence(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        EXECUTING = 'executing', 'Executing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        MISSED = 'missed', 'Missed'
        SKIPPED = 'skipped', 'Skipped'
        CANCELED = 'canceled', 'Canceled'

    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name='occurrences')
    due_at = models.DateTimeField()
    display_timezone = models.CharField(max_length=255)
    schedule_version = models.PositiveIntegerField()
    content_resolved = models.BooleanField(default=False)
    resolved_content = models.TextField(blank=True, null=True)
    resolved_tweet_entry = models.ForeignKey(TweetEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    cancel_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class OccurrenceAttempt(models.Model):
    class PostResult(models.TextChoices):
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        VALIDATION_FAILED = 'validation_failed', 'Validation Failed'

    occurrence = models.ForeignKey(Occurrence, on_delete=models.CASCADE, related_name='attempts')
    target_account = models.ForeignKey(PostingAccount, on_delete=models.CASCADE)
    automatic_attempt_seq = models.PositiveIntegerField(default=1)

    resolved_content = models.TextField(blank=True, null=True)
    resolved_tweet_entry = models.ForeignKey(TweetEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    validation_ok = models.BooleanField(default=False)
    post_result = models.CharField(max_length=20, choices=PostResult.choices, blank=True, null=True)
    error_detail = models.TextField(blank=True)
    external_response_meta = models.JSONField(blank=True, null=True)
    notification_sent = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['occurrence', 'target_account', 'automatic_attempt_seq'], name='unique_occurrence_attempt')
        ]

class RecurringUsageState(models.Model):
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE)
    tweet_entry = models.ForeignKey(TweetEntry, on_delete=models.CASCADE)
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['schedule', 'tweet_entry'], name='unique_recurring_usage')
        ]
