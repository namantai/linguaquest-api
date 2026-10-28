from django.conf import settings
from django.db import models


class UserProgress(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="progress"
    )
    total_xp = models.PositiveIntegerField(default=0)
    completed_exercises = models.ManyToManyField("learning.Exercise", blank=True)

    def __str__(self):
        return f"{self.user}: {self.total_xp} XP"
