from django.db import models

class TweetList(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class TweetEntry(models.Model):
    list = models.ForeignKey(TweetList, on_delete=models.CASCADE, related_name='entries')
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Unique together: (list, text) — but soft, for warning not blocking.
    # We omit UniqueConstraint to allow warning behavior instead of db-level block.

    def __str__(self):
        return f"Entry in {self.list.name}"
