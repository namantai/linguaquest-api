from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections, connection, connections

from learning.models import Lesson, Submission
from learning.services import submit_answer
from progress.models import UserProgress

pytestmark = pytest.mark.django_db


def test_empty_progress(authenticated_client):
    assert authenticated_client.get("/api/v1/me/progress/").data == {
        "total_xp": 0,
        "completed_exercise_ids": [],
        "completed_lesson_ids": [],
        "completed_exercise_count": 0,
        "completed_lesson_count": 0,
    }


def test_repeat_answers_award_xp_once(authenticated_client, exercise):
    url = f"/api/v1/exercises/{exercise.pk}/submit/"
    first = authenticated_client.post(url, {"answer": "b"}, format="json")
    repeat = authenticated_client.post(url, {"answer": "b"}, format="json")
    wrong = authenticated_client.post(url, {"answer": "a"}, format="json")
    assert first.data["xp_awarded"] == 10
    assert repeat.data["xp_awarded"] == wrong.data["xp_awarded"] == 0
    assert Submission.objects.count() == 3
    progress = authenticated_client.get("/api/v1/me/progress/").data
    assert progress["total_xp"] == 10 and progress["completed_exercise_count"] == 1


def test_lesson_requires_every_exercise(
    authenticated_client, course, lesson, exercise, text_exercise
):
    empty_lesson = Lesson.objects.create(course=course, title="Empty lesson", order=2)
    authenticated_client.post(
        f"/api/v1/exercises/{exercise.pk}/submit/", {"answer": "b"}, format="json"
    )
    assert (
        authenticated_client.get("/api/v1/me/progress/").data["completed_lesson_ids"]
        == []
    )
    authenticated_client.post(
        f"/api/v1/exercises/{text_exercise.pk}/submit/", {"answer": "am"}, format="json"
    )
    progress = authenticated_client.get("/api/v1/me/progress/").data
    assert progress["completed_lesson_ids"] == [lesson.pk]
    assert empty_lesson.pk not in progress["completed_lesson_ids"]
    assert progress["total_xp"] == 20


def test_progress_is_per_user(authenticated_client, other_user, exercise):
    submit_answer(user=other_user, exercise=exercise, answer="b")
    assert authenticated_client.get("/api/v1/me/progress/").data["total_xp"] == 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_correct_answers_award_once(user, exercise):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL is required to verify row locking.")
    barrier = Barrier(2)

    def submit():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return submit_answer(user=user, exercise=exercise, answer="b").xp_awarded
        finally:
            # Close this thread's connections even when they are still healthy.
            # close_old_connections() retains them until CONN_MAX_AGE expires.
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        awards = list(pool.map(lambda _: submit(), range(2)))
    assert sorted(awards) == [0, 10]
    assert UserProgress.objects.get(user=user).total_xp == 10
    assert Submission.objects.filter(user=user).count() == 2
