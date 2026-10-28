import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command

from learning.models import Course, Exercise, Lesson, Submission

pytestmark = pytest.mark.django_db


def test_public_courses_lessons_and_exercises(api_client, course, lesson, exercise):
    response = api_client.get("/api/v1/courses/")
    assert response.status_code == 200
    assert response.data["results"][0]["id"] == course.pk
    assert api_client.get(f"/api/v1/courses/{course.pk}/").status_code == 200
    lessons = api_client.get(f"/api/v1/courses/{course.pk}/lessons/").data["results"]
    assert lessons[0]["id"] == lesson.pk
    assert api_client.get(f"/api/v1/lessons/{lesson.pk}/").data["title"] == lesson.title
    exercises = api_client.get(f"/api/v1/lessons/{lesson.pk}/exercises/").data[
        "results"
    ]
    assert exercises[0]["options"] == exercise.options
    assert "correct_answer" not in exercises[0]


def test_unpublished_content_is_hidden(
    api_client, authenticated_client, course, lesson, exercise
):
    course.is_published = False
    course.save()
    assert api_client.get("/api/v1/courses/").data["count"] == 0
    for path in [
        f"/api/v1/courses/{course.pk}/",
        f"/api/v1/courses/{course.pk}/lessons/",
        f"/api/v1/lessons/{lesson.pk}/",
        f"/api/v1/lessons/{lesson.pk}/exercises/",
    ]:
        assert api_client.get(path).status_code == 404
    assert (
        authenticated_client.post(
            f"/api/v1/exercises/{exercise.pk}/submit/", {"answer": "b"}, format="json"
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/courses/999/",
        "/api/v1/courses/999/lessons/",
        "/api/v1/lessons/999/exercises/",
    ],
)
def test_missing_parent_returns_404(api_client, path):
    assert api_client.get(path).status_code == 404


@pytest.mark.parametrize("answer,correct,xp", [("a", False, 0), ("b", True, 10)])
def test_submit_choice(authenticated_client, exercise, user, answer, correct, xp):
    response = authenticated_client.post(
        f"/api/v1/exercises/{exercise.pk}/submit/", {"answer": answer}, format="json"
    )
    assert response.status_code == 201
    assert response.data["status"] == "completed"
    assert response.data["is_correct"] is correct
    assert response.data["xp_awarded"] == xp
    assert "correct_answer" not in response.data
    saved = Submission.objects.get(pk=response.data["id"])
    assert saved.user == user and saved.answer == answer
    assert authenticated_client.get(response["Location"]).status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"answer": ""},
        {"answer": " "},
        {"answer": "x"},
        {"answer": "a" * 2001},
        {"answer": ["b"]},
        {"answer": None},
    ],
)
def test_invalid_submission_not_saved(authenticated_client, exercise, payload):
    response = authenticated_client.post(
        f"/api/v1/exercises/{exercise.pk}/submit/", payload, format="json"
    )
    assert response.status_code == 400
    assert not Submission.objects.exists()


def test_anonymous_cannot_submit(api_client, exercise):
    assert (
        api_client.post(
            f"/api/v1/exercises/{exercise.pk}/submit/", {"answer": "b"}, format="json"
        ).status_code
        == 401
    )


def test_submission_ownership(authenticated_client, other_user, exercise):
    submission = Submission.objects.create(
        user=other_user, exercise=exercise, answer="b", status="completed"
    )
    assert (
        authenticated_client.get(f"/api/v1/submissions/{submission.pk}/").status_code
        == 404
    )


def test_text_normalization_and_wrong_answer(authenticated_client, text_exercise):
    url = f"/api/v1/exercises/{text_exercise.pk}/submit/"
    assert (
        authenticated_client.post(url, {"answer": "is"}, format="json").data[
            "is_correct"
        ]
        is False
    )
    result = authenticated_client.post(url, {"answer": "  AM  "}, format="json")
    assert result.data["is_correct"] is True and result.data["xp_awarded"] == 10


def test_seed_is_repeatable():
    call_command("seed_lessons")
    call_command("seed_lessons")
    assert Course.objects.count() == 1
    assert Lesson.objects.count() == 2
    assert Exercise.objects.count() == 3
    for exercise in Exercise.objects.all():
        exercise.full_clean()


def test_admin_content_validation(exercise, writing_exercise):
    exercise.correct_answer = "missing-option"
    with pytest.raises(ValidationError):
        exercise.full_clean()
    writing_exercise.correct_answer = "hidden-key"
    with pytest.raises(ValidationError):
        writing_exercise.full_clean()
