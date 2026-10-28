from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Course(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    level = models.CharField(
        max_length=2, choices=[(x, x) for x in ["A1", "A2", "B1", "B2"]]
    )
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.title


class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["course", "order"], name="unique_lesson_order"
            )
        ]

    def __str__(self):
        return self.title


class Exercise(models.Model):
    class Kind(models.TextChoices):
        MULTIPLE_CHOICE = "multiple_choice", "Multiple choice"
        TEXT = "text", "Exact text answer"
        WRITING = "writing", "AI writing feedback"

    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE, related_name="exercises"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    prompt = models.TextField(max_length=2000)
    # Example: {"a": "go", "b": "goes"}. Clients submit the option key.
    options = models.JSONField(default=dict, blank=True)
    correct_answer = models.CharField(max_length=2000, blank=True)
    xp_reward = models.PositiveIntegerField(
        default=10, validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["lesson", "order"], name="unique_exercise_order"
            ),
            models.CheckConstraint(
                condition=models.Q(xp_reward__gte=1, xp_reward__lte=100),
                name="exercise_xp_range",
            ),
        ]

    def clean(self):
        super().clean()
        if self.kind == self.Kind.MULTIPLE_CHOICE:
            if (
                not isinstance(self.options, dict)
                or not 2 <= len(self.options) <= 8
                or not all(
                    isinstance(key, str)
                    and 1 <= len(key) <= 32
                    and key == key.strip()
                    and isinstance(value, str)
                    and value.strip()
                    for key, value in self.options.items()
                )
            ):
                raise ValidationError({"options": "Provide 2–8 nonempty text options."})
            if self.correct_answer not in self.options:
                raise ValidationError({"correct_answer": "Use an option key."})
        elif self.kind == self.Kind.TEXT:
            if not self.correct_answer.strip():
                raise ValidationError({"correct_answer": "A text answer is required."})
            if self.options:
                raise ValidationError({"options": "Text exercises do not use options."})
        elif self.kind == self.Kind.WRITING:
            if self.correct_answer or self.options:
                raise ValidationError(
                    "Writing exercises have no answer key or options."
                )

    def __str__(self):
        return f"{self.lesson}: {self.prompt[:60]}"


class Submission(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Queued"
        PROCESSING = "processing", "Processing"
        RETRYING = "retrying", "Retrying"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        UNAVAILABLE = "unavailable", "AI not configured"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    exercise = models.ForeignKey(
        Exercise, on_delete=models.PROTECT, related_name="submissions"
    )
    answer = models.TextField(max_length=2000)
    status = models.CharField(max_length=16, choices=Status.choices)
    is_correct = models.BooleanField(null=True, default=None)
    xp_awarded = models.PositiveIntegerField(default=0)
    feedback = models.JSONField(null=True, blank=True)
    provider = models.CharField(max_length=16, blank=True)
    error_code = models.CharField(max_length=40, blank=True)
    # A lease prevents duplicate task delivery from saving conflicting results.
    processing_token = models.UUIDField(null=True, editable=False)
    processing_started_at = models.DateTimeField(null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "exercise"], name="submission_user_exercise"),
            models.Index(
                fields=["status", "updated_at"], name="submission_status_time"
            ),
        ]
