from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.auth import create_demo_jwt, encode_demo_jwt, validate_demo_jwt
from app.core.config import Settings
from app.core.errors import UnauthorizedError


def test_create_and_validate_demo_jwt() -> None:
    settings = Settings(auth_demo_secret="test-secret")
    now = datetime(2026, 1, 1, tzinfo=UTC)

    token = create_demo_jwt(
        settings=settings,
        tenant_id="tenant-a",
        subject="user-1",
        scopes=("evaluations:read", "evaluations:write"),
        now=now,
    )

    context = validate_demo_jwt(token, settings=settings, now=now + timedelta(minutes=1))

    assert context.tenant_id == "tenant-a"
    assert context.subject == "user-1"
    assert context.scopes == ("evaluations:read", "evaluations:write")


def test_validate_demo_jwt_rejects_bad_signature() -> None:
    token = create_demo_jwt(
        settings=Settings(auth_demo_secret="right-secret"),
        tenant_id="tenant-a",
        subject="user-1",
    )

    with pytest.raises(UnauthorizedError):
        validate_demo_jwt(token, settings=Settings(auth_demo_secret="wrong-secret"))


def test_validate_demo_jwt_rejects_expired_token() -> None:
    settings = Settings(auth_demo_secret="test-secret")
    now = datetime(2026, 1, 1, tzinfo=UTC)
    token = create_demo_jwt(
        settings=settings,
        tenant_id="tenant-a",
        subject="user-1",
        expires_delta=timedelta(minutes=5),
        now=now,
    )

    with pytest.raises(UnauthorizedError):
        validate_demo_jwt(token, settings=settings, now=now + timedelta(minutes=6))


def test_validate_demo_jwt_rejects_wrong_issuer() -> None:
    settings = Settings(auth_demo_secret="test-secret")
    token = encode_demo_jwt(
        payload={
            "iss": "wrong-issuer",
            "aud": settings.auth_audience,
            "sub": "user-1",
            "tenant_id": "tenant-a",
            "exp": 2_000_000_000,
        },
        secret=settings.auth_demo_secret,
    )

    with pytest.raises(UnauthorizedError):
        validate_demo_jwt(token, settings=settings)


def test_validate_demo_jwt_rejects_wrong_audience() -> None:
    settings = Settings(auth_demo_secret="test-secret")
    token = encode_demo_jwt(
        payload={
            "iss": settings.auth_issuer,
            "aud": "wrong-audience",
            "sub": "user-1",
            "tenant_id": "tenant-a",
            "exp": 2_000_000_000,
        },
        secret=settings.auth_demo_secret,
    )

    with pytest.raises(UnauthorizedError):
        validate_demo_jwt(token, settings=settings)


def test_validate_demo_jwt_rejects_missing_subject() -> None:
    settings = Settings(auth_demo_secret="test-secret")
    token = encode_demo_jwt(
        payload={
            "iss": settings.auth_issuer,
            "aud": settings.auth_audience,
            "tenant_id": "tenant-a",
            "exp": 2_000_000_000,
        },
        secret=settings.auth_demo_secret,
    )

    with pytest.raises(UnauthorizedError):
        validate_demo_jwt(token, settings=settings)
