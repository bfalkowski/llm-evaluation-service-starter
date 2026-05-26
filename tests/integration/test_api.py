import time
from datetime import timedelta
from typing import cast

from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient

from app.core.auth import create_demo_jwt
from app.core.config import Settings
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


def auth_headers(
    monkeypatch: MonkeyPatch,
    *,
    tenant_id: str,
    subject: str = "user-1",
) -> dict[str, str]:
    monkeypatch.setenv("APP_AUTH_ENABLED", "true")
    monkeypatch.setenv("APP_AUTH_DEMO_SECRET", "test-secret")
    settings = Settings(auth_enabled=True, auth_demo_secret="test-secret")
    token = create_demo_jwt(
        settings=settings,
        tenant_id=tenant_id,
        subject=subject,
        scopes=("evaluations:read", "evaluations:write"),
        expires_delta=timedelta(minutes=30),
    )
    return {"authorization": f"Bearer {token}"}


def test_health_endpoints() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        assert client.get("/health/ready").json() == {"status": "ready"}


def test_health_endpoints_are_not_rate_limited(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_RATE_LIMIT_SUBMIT_PER_MINUTE", "1")
    with TestClient(create_app()) as client:
        for _ in range(3):
            assert client.get("/health/live").status_code == 200
            assert client.get("/health/ready").status_code == 200


def test_metrics_endpoint_reports_requests_and_jobs() -> None:
    with TestClient(create_app()) as client:
        job = submit_evaluation(client, tenant_id="tenant-a", project_id="project-a")
        for _ in range(20):
            response = client.get(
                f"/v1/evaluations/{job['job_id']}",
                params={"tenant_id": "tenant-a"},
            )
            assert response.status_code == 200
            if response.json()["status"] == "succeeded":
                break
            time.sleep(0.05)

        metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200
    assert metrics_response.headers["content-type"].startswith("text/plain")
    body = metrics_response.text
    assert "# TYPE http_requests_total counter" in body
    assert 'http_requests_total{method="POST",route="/v1/evaluations",status_code="202"}' in body
    assert 'evaluation_jobs_total{status="queued"}' in body
    assert "# TYPE evaluation_scoring_duration_seconds_count counter" in body


def test_auto_create_schema_setting_defaults_to_enabled(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("APP_AUTO_CREATE_SCHEMA", raising=False)
    from app.core.config import get_settings

    assert get_settings().auto_create_schema is True


def test_auto_create_schema_setting_can_be_disabled(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_AUTO_CREATE_SCHEMA", "false")
    from app.core.config import get_settings

    assert get_settings().auto_create_schema is False


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
            status_response = client.get(
                f"/v1/evaluations/{body['job_id']}",
                params={"tenant_id": "tenant-a"},
            )
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
        response = client.get("/v1/evaluations?tenant_id=tenant-a&limit=101")

    assert response.status_code == 422


def test_list_evaluations_requires_tenant_id() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/v1/evaluations")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_submit_evaluation_rate_limit_returns_429(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_RATE_LIMIT_SUBMIT_PER_MINUTE", "1")
    with TestClient(create_app()) as client:
        first = submit_evaluation(client, tenant_id="tenant-a", project_id="project-a")
        second_response = client.post(
            "/v1/evaluations",
            json={
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "question": "Why use OpenTelemetry?",
                "answer": "OpenTelemetry helps collect traces.",
            },
        )

    assert first["status"] == "queued"
    assert second_response.status_code == 429
    body = second_response.json()
    assert body["error"]["code"] == "rate_limit_exceeded"
    assert "request_id" in body["error"]


def test_rate_limit_can_be_disabled(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("APP_RATE_LIMIT_SUBMIT_PER_MINUTE", "1")
    with TestClient(create_app()) as client:
        first = submit_evaluation(client, tenant_id="tenant-a", project_id="project-a")
        second = submit_evaluation(client, tenant_id="tenant-a", project_id="project-a")

    assert first["status"] == "queued"
    assert second["status"] == "queued"


def test_list_evaluations_rate_limit_returns_429(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_RATE_LIMIT_LIST_PER_MINUTE", "1")
    with TestClient(create_app()) as client:
        first_response = client.get("/v1/evaluations?tenant_id=tenant-a")
        second_response = client.get("/v1/evaluations?tenant_id=tenant-a")

    assert first_response.status_code == 200
    assert second_response.status_code == 429


def test_get_missing_evaluation_returns_consistent_error() -> None:
    with TestClient(create_app()) as client:
        response = client.get(
            "/v1/evaluations/00000000-0000-0000-0000-000000000000",
            params={"tenant_id": "tenant-a"},
        )

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert "request_id" in body["error"]


def test_get_evaluation_requires_tenant_id() -> None:
    with TestClient(create_app()) as client:
        job = submit_evaluation(client, tenant_id="tenant-a", project_id="project-a")
        response = client.get(f"/v1/evaluations/{job['job_id']}")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_get_evaluation_hides_cross_tenant_job() -> None:
    with TestClient(create_app()) as client:
        job = submit_evaluation(client, tenant_id="tenant-a", project_id="project-a")
        response = client.get(
            f"/v1/evaluations/{job['job_id']}",
            params={"tenant_id": "tenant-b"},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_get_evaluation_details_returns_request_content() -> None:
    with TestClient(create_app()) as client:
        job = submit_evaluation(
            client,
            tenant_id="tenant-a",
            project_id="project-a",
            question="What changed?",
            answer="The detail endpoint returns authorized request content.",
        )
        response = client.get(
            f"/v1/evaluations/{job['job_id']}/details",
            params={"tenant_id": "tenant-a"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["request"]["question"] == "What changed?"
    assert body["request"]["answer"] == "The detail endpoint returns authorized request content."
    assert body["request"]["rubric"] == "Mention traces."


def test_get_evaluation_details_requires_tenant_id() -> None:
    with TestClient(create_app()) as client:
        job = submit_evaluation(client, tenant_id="tenant-a", project_id="project-a")
        response = client.get(f"/v1/evaluations/{job['job_id']}/details")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_get_evaluation_details_hides_cross_tenant_job() -> None:
    with TestClient(create_app()) as client:
        job = submit_evaluation(client, tenant_id="tenant-a", project_id="project-a")
        response = client.get(
            f"/v1/evaluations/{job['job_id']}/details",
            params={"tenant_id": "tenant-b"},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_validation_error_is_deterministic() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/v1/evaluations", json={"tenant_id": "tenant-a"})

    assert response.status_code == 422


def test_auth_enabled_requires_bearer_token(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_AUTH_ENABLED", "true")
    with TestClient(create_app()) as client:
        response = client.get("/v1/evaluations")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_auth_enabled_rejects_invalid_bearer_token(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_AUTH_ENABLED", "true")
    with TestClient(create_app()) as client:
        response = client.get(
            "/v1/evaluations",
            headers={"authorization": "Bearer not-a-token"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_auth_enabled_submit_and_get_use_token_tenant(monkeypatch: MonkeyPatch) -> None:
    headers = auth_headers(monkeypatch, tenant_id="tenant-a")
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/evaluations",
            json={
                "tenant_id": "tenant-b",
                "project_id": "project-a",
                "question": "Why use OpenTelemetry?",
                "answer": "OpenTelemetry helps collect traces.",
            },
            headers=headers,
        )
        assert response.status_code == 202
        body = response.json()

        status_response = client.get(f"/v1/evaluations/{body['job_id']}", headers=headers)

    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["tenant_id"] == "tenant-a"
    assert status_body["request"]["tenant_id"] == "tenant-a"


def test_auth_enabled_list_uses_token_tenant(monkeypatch: MonkeyPatch) -> None:
    headers = auth_headers(monkeypatch, tenant_id="tenant-a")
    with TestClient(create_app()) as client:
        created = client.post(
            "/v1/evaluations",
            json={
                "project_id": "project-a",
                "question": "Why use OpenTelemetry?",
                "answer": "OpenTelemetry helps collect traces.",
            },
            headers=headers,
        )
        assert created.status_code == 202
        response = client.get(
            "/v1/evaluations",
            params={"tenant_id": "tenant-b"},
            headers=headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert [job["tenant_id"] for job in body["jobs"]] == ["tenant-a"]


def test_auth_enabled_hides_cross_tenant_job(monkeypatch: MonkeyPatch) -> None:
    tenant_a_headers = auth_headers(monkeypatch, tenant_id="tenant-a")
    tenant_b_headers = auth_headers(monkeypatch, tenant_id="tenant-b")
    with TestClient(create_app()) as client:
        created = client.post(
            "/v1/evaluations",
            json={
                "project_id": "project-a",
                "question": "Why use OpenTelemetry?",
                "answer": "OpenTelemetry helps collect traces.",
            },
            headers=tenant_a_headers,
        )
        assert created.status_code == 202

        response = client.get(
            f"/v1/evaluations/{created.json()['job_id']}",
            headers=tenant_b_headers,
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
