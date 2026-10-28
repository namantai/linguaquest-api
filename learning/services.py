import unicodedata

from django.conf import settings
from django.db import transaction

from ai_feedback.services import provider_is_available
from progress.services import award_xp

from .models import Exercise, Submission


def normalize_answer(answer):
    return " ".join(unicodedata.normalize("NFKC", answer).casefold().split())


@transaction.atomic
def submit_answer(*, user, exercise, answer):
    if exercise.kind == Exercise.Kind.WRITING:
        from ai_feedback.tasks import enqueue_feedback

        provider = settings.AI_FEEDBACK_PROVIDER
        available = provider_is_available(provider)
        submission = Submission.objects.create(
            user=user,
            exercise=exercise,
            answer=answer,
            provider=provider,
            status=Submission.Status.PENDING
            if available
            else Submission.Status.UNAVAILABLE,
            error_code="" if available else "ai_not_configured",
        )
        if available:
            transaction.on_commit(lambda: enqueue_feedback(submission.pk))
        return submission

    if exercise.kind == Exercise.Kind.MULTIPLE_CHOICE:
        correct = answer == exercise.correct_answer
    else:
        correct = normalize_answer(answer) == normalize_answer(exercise.correct_answer)
    submission = Submission.objects.create(
        user=user,
        exercise=exercise,
        answer=answer,
        status=Submission.Status.COMPLETED,
        is_correct=correct,
    )
    if correct:
        submission.xp_awarded = award_xp(submission)
        submission.save(update_fields=["xp_awarded", "updated_at"])
    return submission
