from django.db import models
from .accounts import PostingAccount
from .schedules import Schedule
from .execution import Occurrence

class HistoryEvent(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    event_type = models.CharField(max_length=255)
    account = models.ForeignKey(PostingAccount, on_delete=models.SET_NULL, null=True, blank=True)
    schedule = models.ForeignKey(Schedule, on_delete=models.SET_NULL, null=True, blank=True)
    occurrence = models.ForeignKey(Occurrence, on_delete=models.SET_NULL, null=True, blank=True)
    content_summary = models.CharField(max_length=255, blank=True)
    result_status = models.CharField(max_length=100, blank=True)
    detail = models.JSONField(blank=True, null=True)
    correlation_id = models.CharField(max_length=100, blank=True)
