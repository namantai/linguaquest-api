from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from ai_feedback.services import provider_is_available
from ai_feedback.tasks import LEASE_DURATION, enqueue_feedback
from learning.models import Exercise, Submission


class Command(BaseCommand):
    help = (
        "Requeue one failed or stale AI submission after fixing the underlying issue."
    )

    def add_arguments(self, parser):
        parser.add_argument("submission_id", type=int)

    @transaction.atomic
    def handle(self, *args, **options):
        submission = (
            Submission.objects.select_for_update()
            .filter(pk=options["submission_id"], exercise__kind=Exercise.Kind.WRITING)
            .first()
        )
        if not submission:
            raise CommandError("Writing submission not found.")
        if submission.status == Submission.Status.COMPLETED:
            raise CommandError("Completed submissions cannot be requeued.")
        if not provider_is_available(submission.provider):
            raise CommandError("The submission's original provider is not configured.")
        if (
            submission.status
            in {
                Submission.Status.PROCESSING,
                Submission.Status.PENDING,
                Submission.Status.RETRYING,
            }
            and submission.updated_at > timezone.now() - LEASE_DURATION
        ):
            raise CommandError(
                "Submission is still active. Wait at least five minutes."
            )
        submission.status = Submission.Status.PENDING
        submission.processing_token = None
        submission.processing_started_at = None
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
        transaction.on_commit(lambda: enqueue_feedback(submission.pk))
        self.stdout.write(
            "Submission scheduled for requeue. Poll its status to confirm."
        )
