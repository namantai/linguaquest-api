from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from learning.models import Course, Exercise, Lesson


@pytest.fixture(autouse=True)
def block_real_openai():
    """A forgotten mock must fail rather than issue a paid API call."""
    with patch(
        "ai_feedback.services.OpenAI", side_effect=AssertionError("Real AI disabled")
    ):
        yield


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="student", email="student@example.com", password="Learning!42-pass"
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="other", password="Learning!42-pass")


@pytest.fixture
def authenticated_client(api_client, user):
    # Exercise real JWT authentication instead of force_authenticate.
    tokens = api_client.post(
        "/api/v1/auth/token/",
        {"username": user.username, "password": "Learning!42-pass"},
        format="json",
    ).json()
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return api_client


@pytest.fixture
def course(db):
    return Course.objects.create(title="English basics", level="A1", is_published=True)


@pytest.fixture
def lesson(course):
    return Lesson.objects.create(course=course, title="Introductions", order=1)


@pytest.fixture
def exercise(lesson):
    return Exercise.objects.create(
        lesson=lesson,
        kind=Exercise.Kind.MULTIPLE_CHOICE,
        prompt="She ___ to school.",
        options={"a": "go", "b": "goes"},
        correct_answer="b",
        xp_reward=10,
        order=1,
    )


@pytest.fixture
def text_exercise(lesson):
    return Exercise.objects.create(
        lesson=lesson,
        kind=Exercise.Kind.TEXT,
        prompt="I ___ a student.",
        correct_answer="am",
        order=2,
    )


@pytest.fixture
def writing_exercise(lesson):
    return Exercise.objects.create(
        lesson=lesson,
        kind=Exercise.Kind.WRITING,
        prompt="Describe your morning in two sentences.",
        order=3,
        xp_reward=20,
    )
