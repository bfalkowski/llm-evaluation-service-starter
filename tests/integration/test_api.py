from typing import cast

from fastapi.testclient import TestClient

from app.main import create_app


def submit_evaluation(
    client: TestClient,
    *,
    tenant_id: str,
    project_id: str,
    question: str = "Why use OpenTelemetry?",
    answer: str = "OpenTelemetry helps collect traces and diagnose service behavior.",
) -> dict[str, object]:
    response = client.post(
        "/v1/evaluations",
        json={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "question": question,
            "answer": answer,
            "rubric": "Mention traces.",
        },
    )
    assert response.status_code == 202
    return cast(dict[str, object], response.json())


def test_health_endpoints() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        assert client.get("/health/ready").json() == {"status": "ready"}


def test_readiness_reports_unhealthy_repository() -> None:
    class UnhealthyRepository:
        async def health_check(self) -> bool:
            return False

    app = create_app()
    with TestClient(app) as client:
        app.state.repository = UnhealthyRepository()
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_cors_allows_local_dashboard_origin() -> None:
    with TestClient(create_app()) as client:
        response = client.options(
            "/v1/evaluations",
            headers={
                "origin": "http://localhost:5173",
                "access-control-request-method": "POST",
                "access-control-request-headers": "content-type,x-request-id",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()
    assert "x-request-id" in response.headers["access-control-allow-headers"].lower()


def test_cors_rejects_unknown_origin() -> None:
    with TestClient(create_app()) as client:
        response = client.options(
            "/v1/evaluations",
            headers={
                "origin": "https://example.com",
                "access-control-request-method": "POST",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_submit_and_get_evaluation() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/evaluations",
            json={
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "question": "Why use OpenTelemetry?",
                "answer": "OpenTelemetry helps collect traces and diagnose service behavior.",
                "rubric": "Mention traces.",
            },
            headers={"x-request-id": "test-request-id"},
        )
        assert response.status_code == 202
        assert response.headers["x-request-id"] == "test-request-id"
        body = response.json()
        assert body["status"] == "queued"

        import time

        status_body = None
        for _ in range(20):
            status_response = client.get(f"/v1/evaluations/{body['job_id']}")
            assert status_response.status_code == 200
            status_body = status_response.json()
            if status_body["status"] == "succeeded":
                break
            time.sleep(0.05)

        assert status_body is not None
        assert status_body["job_id"] == body["job_id"]
        assert status_body["status"] == "succeeded"
        assert "question" not in status_body.get("request", {})
        assert "answer" not in status_body.get("request", {})


def test_list_evaluations_returns_recent_summaries() -> None:
    with TestClient(create_app()) as client:
        first = submit_evaluation(client, tenant_id="tenant-a", project_id="project-a")
        second = submit_evaluation(client, tenant_id="tenant-a", project_id="project-b")

        response = client.get("/v1/evaluations?tenant_id=tenant-a")

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"]
    assert [job["job_id"] for job in body["jobs"]] == [second["job_id"], first["job_id"]]
    assert all("request" not in job for job in body["jobs"])
    assert all("question" not in job for job in body["jobs"])
    assert all("answer" not in job for job in body["jobs"])


def test_list_evaluations_filters_by_project_and_limit() -> None:
    with TestClient(create_app()) as client:
        submit_evaluation(client, tenant_id="tenant-a", project_id="project-a")
        second = submit_evaluation(client, tenant_id="tenant-a", project_id="project-b")
        third = submit_evaluation(client, tenant_id="tenant-a", project_id="project-b")
        submit_evaluation(client, tenant_id="tenant-b", project_id="project-b")

        response = client.get(
            "/v1/evaluations",
            params={"tenant_id": "tenant-a", "project_id": "project-b", "limit": 2},
        )

    assert response.status_code == 200
    body = response.json()
    assert [job["job_id"] for job in body["jobs"]] == [third["job_id"], second["job_id"]]
    assert all(job["tenant_id"] == "tenant-a" for job in body["jobs"])
    assert all(job["project_id"] == "project-b" for job in body["jobs"])


def test_list_evaluations_rejects_invalid_limit() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/v1/evaluations?limit=101")

    assert response.status_code == 422


def test_get_missing_evaluation_returns_consistent_error() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/v1/evaluations/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert "request_id" in body["error"]


def test_validation_error_is_deterministic() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/v1/evaluations", json={"tenant_id": "tenant-a"})

    assert response.status_code == 422
