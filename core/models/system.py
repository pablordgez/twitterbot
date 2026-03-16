from django.db import models

class SchedulerLease(models.Model):
    owner_id = models.CharField(max_length=255, unique=True)
    acquired_at = models.DateTimeField(auto_now_add=True)
    renewed_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
