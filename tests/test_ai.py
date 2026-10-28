import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from billiard.exceptions import SoftTimeLimitExceeded
from celery.exceptions import Retry
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from openai import APIConnectionError, APIStatusError, OpenAI
from pydantic import ValidationError

from ai_feedback.services import (
    Feedback,
    InvalidFeedback,
    ProviderUnavailable,
    TransientFeedbackError,
    generate_feedback,
)
from ai_feedback.tasks import (
    claim_submission,
    complete_submission,
    enqueue_feedback,
    process_feedback,
)
from learning.models import Submission
from progress.models import UserProgress

pytestmark = pytest.mark.django_db


@pytest.fixture
def pending_submission(user, writing_exercise):
    return Submission.objects.create(
        user=user,
        exercise=writing_exercise,
        answer="I study every morning.",
        status="pending",
        provider="mock",
    )


@pytest.fixture
def sdk_client(settings):
    settings.AI_FEEDBACK_PROVIDER = "openai"
    settings.OPENAI_API_KEY = "test-placeholder"
    client = MagicMock()
    with patch("ai_feedback.services.OpenAI") as constructor:
        constructor.return_value.__enter__.return_value = client
        yield client


def test_mock_is_explicit():
    result = generate_feedback(
        prompt="Write a sentence.", answer="Hello.", provider="mock"
    )
    assert result.score == 80
    assert "Mock" in result.explanation and "No AI" in result.explanation


@pytest.mark.parametrize("answer", ["", " ", "x" * 2001])
def test_service_limits_input(answer):
    with pytest.raises(InvalidFeedback):
        generate_feedback(prompt="Write.", answer=answer, provider="mock")


def test_missing_key_is_unavailable(settings):
    settings.AI_FEEDBACK_PROVIDER = "openai"
    with pytest.raises(ProviderUnavailable):
        generate_feedback(prompt="Write.", answer="Hello.", provider="openai")


def test_openai_structured_feedback(sdk_client, settings):
    sdk_client.responses.parse.return_value = SimpleNamespace(
        output_parsed=Feedback(
            score=65,
            corrections=["Use 'goes' with 'she'."],
            explanation="Add s for he or she.",
        )
    )
    result = generate_feedback(
        prompt="Write a routine.", answer="She go.", provider="openai"
    )
    assert result.score == 65 and result.corrections
    kwargs = sdk_client.responses.parse.call_args.kwargs
    assert kwargs["model"] == settings.OPENAI_MODEL
    assert kwargs["text_format"] is Feedback
    assert kwargs["store"] is False


def test_openai_refusal_is_failure(sdk_client):
    sdk_client.responses.parse.return_value = SimpleNamespace(output_parsed=None)
    with pytest.raises(InvalidFeedback):
        generate_feedback(prompt="Write.", answer="Hello.", provider="openai")


def test_real_sdk_parses_mock_http_response(settings):
    """Exercise SDK serialization/parsing through an offline HTTP transport."""
    settings.AI_FEEDBACK_PROVIDER = "openai"
    settings.OPENAI_API_KEY = "test-placeholder"

    def respond(request):
        body = json.loads(request.content)
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        assert body["store"] is False
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 0,
                "model": settings.OPENAI_MODEL,
                "status": "completed",
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "annotations": [],
                                "text": json.dumps(
                                    {
                                        "score": 85,
                                        "corrections": [],
                                        "explanation": "Good work.",
                                    }
                                ),
                            }
                        ],
                    }
                ],
            },
        )

    client = OpenAI(
        api_key="test-placeholder",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    )
    with patch("ai_feedback.services.OpenAI", return_value=client):
        feedback = generate_feedback(
            prompt="Write.", answer="Hello.", provider="openai"
        )
    assert feedback.score == 85


@pytest.mark.parametrize("score", [-1, 101, "80", True])
def test_feedback_score_is_validated(score):
    with pytest.raises(ValidationError):
        Feedback(score=score, corrections=[], explanation="Feedback.")


@pytest.mark.parametrize(
    "status_code,exception",
    [
        (429, TransientFeedbackError),
        (500, TransientFeedbackError),
        (401, InvalidFeedback),
    ],
)
def test_provider_http_errors(sdk_client, status_code, exception):
    response = httpx.Response(
        status_code, request=httpx.Request("POST", "https://example.com")
    )
    sdk_client.responses.parse.side_effect = APIStatusError(
        "sensitive provider details", response=response, body=None
    )
    with pytest.raises(exception):
        generate_feedback(prompt="Write.", answer="Hello.", provider="openai")


def test_connection_error_is_retryable(sdk_client):
    sdk_client.responses.parse.side_effect = APIConnectionError(
        request=httpx.Request("POST", "https://example.com")
    )
    with pytest.raises(TransientFeedbackError):
        generate_feedback(prompt="Write.", answer="Hello.", provider="openai")


def test_task_stores_feedback_and_deduplicates(pending_submission):
    process_feedback.apply(args=[pending_submission.pk], throw=True)
    process_feedback.apply(args=[pending_submission.pk], throw=True)
    pending_submission.refresh_from_db()
    assert pending_submission.status == "completed"
    assert pending_submission.feedback["score"] == 80
    assert pending_submission.provider == "mock"
    assert pending_submission.xp_awarded == 20
    assert UserProgress.objects.get(user=pending_submission.user).total_xp == 20


def test_low_ai_score_does_not_award(pending_submission):
    with patch(
        "ai_feedback.tasks.generate_feedback",
        return_value=Feedback(
            score=40, corrections=["Use present simple."], explanation="Try again."
        ),
    ):
        process_feedback.apply(args=[pending_submission.pk], throw=True)
    pending_submission.refresh_from_db()
    assert pending_submission.is_correct is False
    assert pending_submission.xp_awarded == 0
    assert not UserProgress.objects.exists()


def test_active_duplicate_task_does_not_call_provider(pending_submission):
    claim_submission(pending_submission.pk)
    with patch("ai_feedback.tasks.generate_feedback") as provider:
        process_feedback.apply(args=[pending_submission.pk], throw=True)
    provider.assert_not_called()


def test_stale_worker_cannot_overwrite_new_result(pending_submission):
    old_claim = claim_submission(pending_submission.pk)
    Submission.objects.filter(pk=pending_submission.pk).update(
        processing_started_at=timezone.now() - timedelta(minutes=6)
    )
    new_claim = claim_submission(pending_submission.pk)
    feedback = Feedback(score=90, corrections=[], explanation="Good work.")
    complete_submission(old_claim, feedback)
    pending_submission.refresh_from_db()
    assert pending_submission.status == "processing"
    complete_submission(new_claim, feedback)
    pending_submission.refresh_from_db()
    assert pending_submission.status == "completed"
    assert pending_submission.xp_awarded == 20


def test_provider_error_is_sanitized(pending_submission):
    with patch(
        "ai_feedback.tasks.generate_feedback",
        side_effect=RuntimeError("SECRET API KEY"),
    ):
        process_feedback.apply(args=[pending_submission.pk], throw=True)
    pending_submission.refresh_from_db()
    assert pending_submission.status == "failed"
    assert pending_submission.error_code == "feedback_failed"
    assert pending_submission.feedback is None


def test_soft_timeout_is_recorded(pending_submission):
    with patch(
        "ai_feedback.tasks.generate_feedback", side_effect=SoftTimeLimitExceeded
    ):
        process_feedback.apply(args=[pending_submission.pk], throw=True)
    pending_submission.refresh_from_db()
    assert pending_submission.status == "failed"
    assert pending_submission.error_code == "provider_timeout"


def test_retry_publish_failure_is_recorded(pending_submission):
    with (
        patch(
            "ai_feedback.tasks.generate_feedback", side_effect=TransientFeedbackError
        ),
        patch.object(process_feedback, "retry", side_effect=ConnectionError),
    ):
        process_feedback.run(pending_submission.pk)
    pending_submission.refresh_from_db()
    assert pending_submission.status == "failed"
    assert pending_submission.error_code == "queue_unavailable"


def test_transient_failure_retries_then_succeeds(pending_submission):
    feedback = Feedback(score=90, corrections=[], explanation="Good work.")
    with patch(
        "ai_feedback.tasks.generate_feedback",
        side_effect=[TransientFeedbackError(), feedback],
    ):
        process_feedback.apply(args=[pending_submission.pk], throw=False)
    pending_submission.refresh_from_db()
    assert pending_submission.status == "completed"


def test_retry_exhaustion(pending_submission, settings):
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    with patch(
        "ai_feedback.tasks.generate_feedback", side_effect=TransientFeedbackError
    ) as provider:
        process_feedback.apply(args=[pending_submission.pk], throw=False)
    pending_submission.refresh_from_db()
    assert provider.call_count == 4
    assert pending_submission.status == "failed"
    assert pending_submission.error_code == "provider_unavailable"


def test_retry_status_persisted_before_requeue(pending_submission):
    with (
        patch(
            "ai_feedback.tasks.generate_feedback", side_effect=TransientFeedbackError
        ),
        patch.object(process_feedback, "retry", side_effect=Retry),
        pytest.raises(Retry),
    ):
        process_feedback.run(pending_submission.pk)
    pending_submission.refresh_from_db()
    assert pending_submission.status == "retrying"


def test_broker_failure_is_recorded(pending_submission):
    with patch.object(
        process_feedback, "delay", side_effect=ConnectionError("redis secret")
    ):
        enqueue_feedback(pending_submission.pk)
    pending_submission.refresh_from_db()
    assert pending_submission.status == "failed"
    assert pending_submission.error_code == "queue_unavailable"


def test_provider_disabled_after_enqueue(pending_submission, settings):
    settings.AI_FEEDBACK_PROVIDER = "disabled"
    process_feedback.apply(args=[pending_submission.pk], throw=True)
    pending_submission.refresh_from_db()
    assert pending_submission.status == "unavailable"
    assert pending_submission.xp_awarded == 0


def test_api_queues_only_after_commit(
    authenticated_client, writing_exercise, django_capture_on_commit_callbacks
):
    with (
        patch("ai_feedback.tasks.enqueue_feedback") as enqueue,
        django_capture_on_commit_callbacks(execute=True),
    ):
        response = authenticated_client.post(
            f"/api/v1/exercises/{writing_exercise.pk}/submit/",
            {"answer": "I study every day."},
            format="json",
        )
        assert response.status_code == 202
        enqueue.assert_not_called()
    enqueue.assert_called_once_with(response.data["id"])


@pytest.mark.parametrize("provider", ["disabled", "openai"])
def test_api_without_ai_configuration(
    authenticated_client, writing_exercise, settings, provider
):
    settings.AI_FEEDBACK_PROVIDER = provider
    with patch("ai_feedback.tasks.enqueue_feedback") as enqueue:
        response = authenticated_client.post(
            f"/api/v1/exercises/{writing_exercise.pk}/submit/",
            {"answer": "I study every day."},
            format="json",
        )
    assert response.status_code == 201
    assert response.data["status"] == "unavailable"
    assert response.data["error_code"] == "ai_not_configured"
    assert response.data["feedback"] is None
    enqueue.assert_not_called()


def test_writing_poll_flow(
    authenticated_client, writing_exercise, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = authenticated_client.post(
            f"/api/v1/exercises/{writing_exercise.pk}/submit/",
            {"answer": "I study every day."},
            format="json",
        )
    polled = authenticated_client.get(response["Location"])
    assert polled.data["status"] == "completed"
    assert polled.data["provider"] == "mock"
    assert polled.data["feedback"]["score"] == 80


def test_new_writing_submission_does_not_duplicate_xp(
    authenticated_client, writing_exercise, django_capture_on_commit_callbacks
):
    for _ in range(2):
        with django_capture_on_commit_callbacks(execute=True):
            authenticated_client.post(
                f"/api/v1/exercises/{writing_exercise.pk}/submit/",
                {"answer": "I study every day."},
                format="json",
            )
    assert Submission.objects.count() == 2
    assert authenticated_client.get("/api/v1/me/progress/").data["total_xp"] == 20


def test_recovery_rejects_active_task(pending_submission):
    with pytest.raises(CommandError, match="still active"):
        call_command("retry_feedback", pending_submission.pk)


def test_recovery_requeues_failed_task(
    pending_submission, django_capture_on_commit_callbacks
):
    pending_submission.status = "failed"
    pending_submission.save()
    with django_capture_on_commit_callbacks(execute=True):
        call_command("retry_feedback", pending_submission.pk)
    pending_submission.refresh_from_db()
    assert pending_submission.status == "completed"
