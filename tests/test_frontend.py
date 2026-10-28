import pytest
from django.contrib.staticfiles import finders
from django.urls import reverse


@pytest.mark.django_db
def test_homepage_and_frontend_assets(client):
    response = client.get(reverse("home"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "LinguaQuest" in html
    for filename in ["style.css", "api.js", "app.js"]:
        assert f"/static/frontend/{filename}" in html
        assert finders.find(f"frontend/{filename}") is not None
    assert "correct_answer" not in html
