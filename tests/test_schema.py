import pytest
from drf_spectacular.validation import validate_schema


@pytest.mark.django_db
def test_openapi_schema_and_swagger(api_client):
    response = api_client.get("/api/schema/?format=json")
    assert response.status_code == 200
    schema = response.json()
    validate_schema(schema)
    assert "/api/v1/exercises/{id}/submit/" in schema["paths"]
    assert "jwtAuth" in schema["components"]["securitySchemes"]
    assert "correct_answer" not in str(schema)
    assert api_client.get("/api/docs/").status_code == 200
