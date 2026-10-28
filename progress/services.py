from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q

from learning.models import Lesson

from .models import UserProgress


@transaction.atomic
def award_xp(submission):
    """Serialize awards per user, including the very first progress row creation."""
    get_user_model().objects.select_for_update().get(pk=submission.user_id)
    progress, _ = UserProgress.objects.get_or_create(user_id=submission.user_id)
    if progress.completed_exercises.filter(pk=submission.exercise_id).exists():
        return 0
    progress.completed_exercises.add(submission.exercise_id)
    progress.total_xp += submission.exercise.xp_reward
    progress.save(update_fields=["total_xp"])
    return submission.exercise.xp_reward


def get_progress(user):
    progress = UserProgress.objects.filter(user=user).first()
    completed = (
        list(progress.completed_exercises.order_by("id").values_list("id", flat=True))
        if progress
        else []
    )
    # Derive lesson completion so there is no second counter to keep in sync.
    lessons = (
        Lesson.objects.filter(course__is_published=True)
        .annotate(
            exercise_count=Count("exercises"),
            completed_count=Count("exercises", filter=Q(exercises__id__in=completed)),
        )
        .order_by("id")
    )
    completed_lessons = [
        lesson.pk
        for lesson in lessons
        if lesson.exercise_count > 0 and lesson.completed_count == lesson.exercise_count
    ]
    return {
        "total_xp": progress.total_xp if progress else 0,
        "completed_exercise_ids": completed,
        "completed_lesson_ids": completed_lessons,
        "completed_exercise_count": len(completed),
        "completed_lesson_count": len(completed_lessons),
    }
