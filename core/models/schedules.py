from django.db import models
from .accounts import PostingAccount
from .tweets import TweetList

class Schedule(models.Model):
    class ScheduleType(models.TextChoices):
        ONE_TIME = 'one_time', 'One Time'
        RECURRING = 'recurring', 'Recurring'

    class ContentMode(models.TextChoices):
        FIXED_NEW = 'fixed_new', 'Fixed New'
        FIXED_FROM_LIST = 'fixed_from_list', 'Fixed From List'
        RANDOM_FROM_LIST = 'random_from_list', 'Random From List'
        RANDOM_FROM_LISTS = 'random_from_lists', 'Random From Lists'

    class IntervalType(models.TextChoices):
        HOURS = 'hours', 'Hours'
        DAYS = 'days', 'Days'

    class RandomResolutionMode(models.TextChoices):
        SHARED = 'shared', 'Shared'
        PER_ACCOUNT = 'per_account', 'Per Account'

    class ExhaustionBehavior(models.TextChoices):
        STOP = 'stop', 'Stop'
        SKIP = 'skip', 'Skip'
        RESET = 'reset', 'Reset'

    schedule_type = models.CharField(max_length=20, choices=ScheduleType.choices)
    timezone_mode = models.CharField(max_length=50, blank=True)
    timezone_name = models.CharField(max_length=255)
    interval_type = models.CharField(max_length=20, choices=IntervalType.choices, blank=True, null=True)
    interval_value = models.PositiveIntegerField(blank=True, null=True)
    start_datetime = models.DateTimeField()

    content_mode = models.CharField(max_length=30, choices=ContentMode.choices)
    fixed_content = models.TextField(blank=True, null=True)
    random_resolution_mode = models.CharField(max_length=20, choices=RandomResolutionMode.choices, blank=True, null=True)

    reuse_enabled = models.BooleanField(default=False)
    exhaustion_behavior = models.CharField(max_length=20, choices=ExhaustionBehavior.choices, blank=True, null=True)

    status = models.CharField(max_length=20, default='active') # active / canceled
    version = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class ScheduleTargetAccount(models.Model):
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name='target_accounts')
    account = models.ForeignKey(PostingAccount, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['schedule', 'account'], name='unique_schedule_account')
        ]

class ScheduleSourceList(models.Model):
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name='source_lists')
    tweet_list = models.ForeignKey(TweetList, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['schedule', 'tweet_list'], name='unique_schedule_list')
        ]
