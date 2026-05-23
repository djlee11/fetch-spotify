from django.db import models


class Friend(models.Model):
    user_id = models.CharField(max_length=255, unique=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["added_at"]

    def __str__(self):
        return self.user_id
