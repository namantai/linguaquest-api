from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import AccessToken

pytestmark = pytest.mark.django_db


def test_register_hashes_password_and_hides_it(api_client):
    response = api_client.post(
        "/api/v1/auth/register/",
        {
            "username": "new_student",
            "email": "new@example.com",
            "password": "Learning!42-pass",
            "is_staff": True,
        },
        format="json",
    )
    assert response.status_code == 201
    assert "password" not in response.data
    user = User.objects.get(username="new_student")
    assert user.check_password("Learning!42-pass")
    assert not user.is_staff


@pytest.mark.parametrize("password", ["short", "password", "1234567890"])
def test_weak_password_rejected(api_client, password):
    response = api_client.post(
        "/api/v1/auth/register/",
        {
            "username": "new",
            "email": "new@example.com",
            "password": password,
        },
        format="json",
    )
    assert response.status_code == 400
    assert not User.objects.exists()


def test_duplicate_username_and_invalid_email(api_client, user):
    response = api_client.post(
        "/api/v1/auth/register/",
        {
            "username": user.username,
            "email": "invalid",
            "password": "Learning!42-pass",
        },
        format="json",
    )
    assert response.status_code == 400
    assert "username" in response.data and "email" in response.data


def test_login_refresh_and_profile(api_client, user):
    response = api_client.post(
        "/api/v1/auth/token/",
        {
            "username": user.username,
            "password": "Learning!42-pass",
        },
        format="json",
    )
    assert response.status_code == 200
    tokens = response.json()
    refresh = api_client.post(
        "/api/v1/auth/token/refresh/",
        {
            "refresh": tokens["refresh"],
        },
        format="json",
    )
    assert refresh.status_code == 200
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.data['access']}")
    profile = api_client.get("/api/v1/me/")
    assert profile.status_code == 200
    assert profile.data["id"] == user.pk
    assert "password" not in profile.data


def test_invalid_credentials_and_inactive_user(api_client, user):
    response = api_client.post(
        "/api/v1/auth/token/",
        {
            "username": user.username,
            "password": "wrong",
        },
        format="json",
    )
    assert response.status_code == 401
    user.is_active = False
    user.save()
    response = api_client.post(
        "/api/v1/auth/token/",
        {
            "username": user.username,
            "password": "Learning!42-pass",
        },
        format="json",
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "path", ["/api/v1/me/", "/api/v1/me/progress/", "/api/v1/submissions/1/"]
)
def test_private_endpoints_require_token(api_client, path):
    assert api_client.get(path).status_code == 401


def test_expired_and_invalid_tokens(api_client, user):
    token = AccessToken.for_user(user)
    token.set_exp(lifetime=timedelta(seconds=-1))
    for value in [str(token), "invalid"]:
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {value}")
        assert api_client.get("/api/v1/me/").status_code == 401
    api_client.credentials()
    assert (
        api_client.post(
            "/api/v1/auth/token/refresh/", {"refresh": "invalid"}, format="json"
        ).status_code
        == 401
    )
