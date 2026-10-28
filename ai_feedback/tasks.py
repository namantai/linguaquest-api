import logging
import uuid
from datetime import timedelta

from billiard.exceptions import SoftTimeLimitExceeded
from celery import shared_task
from celery.exceptions import Retry
from django.db import transaction
from django.utils import timezone

from learning.models import Exercise, Submission
from progress.services import award_xp

from .services import ProviderUnavailable, TransientFeedbackError, generate_feedback

logger = logging.getLogger(__name__)
LEASE_DURATION = timedelta(minutes=5)


def enqueue_feedback(submission_id):
    try:
        process_feedback.delay(submission_id)
    except Exception as exc:
        # The row has committed. Tell clients it was not queued; never return a
        # provider/broker exception containing connection strings or credentials.
        Submission.objects.filter(
            pk=submission_id, status=Submission.Status.PENDING
        ).update(
            status=Submission.Status.FAILED,
            error_code="queue_unavailable",
            updated_at=timezone.now(),
        )
        logger.warning("Feedback enqueue failed (%s)", type(exc).__name__)


@transaction.atomic
def claim_submission(submission_id):
    submission = Submission.objects.select_for_update().filter(pk=submission_id).first()
    if submission is None or submission.exercise.kind != Exercise.Kind.WRITING:
        return None
    if submission.status == Submission.Status.PROCESSING:
        if submission.processing_started_at > timezone.now() - LEASE_DURATION:
            return None
    elif submission.status not in {
        Submission.Status.PENDING,
        Submission.Status.RETRYING,
    }:
        return None
    submission.status = Submission.Status.PROCESSING
    submission.processing_token = uuid.uuid4()
    submission.processing_started_at = timezone.now()
    submission.error_code = ""
    submission.save(
        update_fields=[
            "status",
            "processing_token",
            "processing_started_at",
            "error_code",
            "updated_at",
        ]
    )
    return submission


def set_task_status(submission, status, error_code):
    return Submission.objects.filter(
        pk=submission.pk, processing_token=submission.processing_token
    ).update(status=status, error_code=error_code, updated_at=timezone.now())


@transaction.atomic
def complete_submission(submission, feedback):
    current = Submission.objects.select_for_update().get(pk=submission.pk)
    if (
        current.processing_token != submission.processing_token
        or current.status != Submission.Status.PROCESSING
    ):
        return
    current.feedback = feedback.model_dump()
    current.is_correct = feedback.score >= 70
    if current.is_correct:
        current.xp_awarded = award_xp(current)
    current.status = Submission.Status.COMPLETED
    current.error_code = ""
    current.save(
        update_fields=[
            "feedback",
            "is_correct",
            "xp_awarded",
            "status",
            "error_code",
            "updated_at",
        ]
    )


@shared_task(bind=True, max_retries=3, soft_time_limit=60, time_limit=90)
def process_feedback(self, submission_id):
    submission = claim_submission(submission_id)
    if submission is None:
        return
    try:
        feedback = generate_feedback(
            prompt=submission.exercise.prompt,
            answer=submission.answer,
            provider=submission.provider,
        )
        complete_submission(submission, feedback)
    except ProviderUnavailable:
        set_task_status(submission, Submission.Status.UNAVAILABLE, "ai_not_configured")
    except TransientFeedbackError:
        if self.request.retries >= self.max_retries:
            set_task_status(
                submission, Submission.Status.FAILED, "provider_unavailable"
            )
            return
        if not set_task_status(
            submission, Submission.Status.RETRYING, "provider_retrying"
        ):
            return
        try:
            raise self.retry(countdown=10 * (2**self.request.retries))
        except Retry:
            raise
        except Exception:
            set_task_status(submission, Submission.Status.FAILED, "queue_unavailable")
    except SoftTimeLimitExceeded:
        set_task_status(submission, Submission.Status.FAILED, "provider_timeout")
    except Exception as exc:
        set_task_status(submission, Submission.Status.FAILED, "feedback_failed")
        logger.warning(
            "Feedback failed for submission %s (%s)", submission_id, type(exc).__name__
        )
