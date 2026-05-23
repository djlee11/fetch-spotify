from django.db import models


class Friend(models.Model):
    owner_id = models.CharField(max_length=255, db_index=True)
    user_id = models.CharField(max_length=255)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["added_at"]
        unique_together = [("owner_id", "user_id")]

    def __str__(self):
        return self.user_id
