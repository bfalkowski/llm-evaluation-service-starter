from fastapi.testclient import TestClient

from app.main import create_app


def test_swagger_docs_page_is_available() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/docs")

    assert response.status_code == 200
    assert "swagger-ui" in response.text
    assert "/openapi.json" in response.text


def test_openapi_schema_includes_evaluation_paths() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "LLM Evaluation Service"
    assert "/v1/evaluations" in schema["paths"]
    assert "/v1/evaluations/{job_id}" in schema["paths"]
