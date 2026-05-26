from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Header

from app.core.config import Settings, get_settings
from app.core.errors import UnauthorizedError


@dataclass(frozen=True)
class RequestContext:
    tenant_id: str
    subject: str
    scopes: tuple[str, ...] = ()


def create_demo_jwt(
    *,
    settings: Settings,
    tenant_id: str,
    subject: str,
    scopes: tuple[str, ...] = (),
    expires_delta: timedelta = timedelta(hours=1),
    now: datetime | None = None,
) -> str:
    current_time = now or datetime.now(UTC)
    payload: dict[str, Any] = {
        "iss": settings.auth_issuer,
        "aud": settings.auth_audience,
        "sub": subject,
        "tenant_id": tenant_id,
        "scopes": list(scopes),
        "iat": int(current_time.timestamp()),
        "exp": int((current_time + expires_delta).timestamp()),
    }
    return encode_demo_jwt(payload=payload, secret=settings.auth_demo_secret)


def encode_demo_jwt(*, payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = ".".join(
        [
            _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(
        secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_base64url_encode(signature)}"


def validate_demo_jwt(
    token: str,
    *,
    settings: Settings,
    now: datetime | None = None,
) -> RequestContext:
    header, payload, signing_input, signature = _decode_token_parts(token)
    if header.get("alg") != "HS256":
        raise UnauthorizedError("Unsupported token algorithm.")

    expected_signature = hmac.new(
        settings.auth_demo_secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(signature, expected_signature):
        raise UnauthorizedError("Invalid token signature.")

    current_time = int((now or datetime.now(UTC)).timestamp())
    if _required_string(payload, "iss") != settings.auth_issuer:
        raise UnauthorizedError("Invalid token issuer.")
    if not _audience_matches(payload.get("aud"), settings.auth_audience):
        raise UnauthorizedError("Invalid token audience.")
    if _required_int(payload, "exp") <= current_time:
        raise UnauthorizedError("Token has expired.")

    return RequestContext(
        tenant_id=_required_string(payload, "tenant_id"),
        subject=_required_string(payload, "sub"),
        scopes=_scopes(payload),
    )


def get_request_context(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> RequestContext | None:
    settings = get_settings()
    if not settings.auth_enabled:
        return None

    if authorization is None:
        raise UnauthorizedError("Missing bearer token.")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise UnauthorizedError("Invalid authorization header.")

    return validate_demo_jwt(token, settings=settings)


def _decode_token_parts(token: str) -> tuple[dict[str, Any], dict[str, Any], str, bytes]:
    parts = token.split(".")
    if len(parts) != 3:
        raise UnauthorizedError("Invalid token format.")

    signing_input = ".".join(parts[:2])
    try:
        header = json.loads(_base64url_decode(parts[0]))
        payload = json.loads(_base64url_decode(parts[1]))
        signature = _base64url_decode(parts[2])
    except (ValueError, json.JSONDecodeError) as exc:
        raise UnauthorizedError("Invalid token encoding.") from exc

    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise UnauthorizedError("Invalid token content.")

    return header, payload, signing_input, signature


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _required_string(payload: dict[str, Any], claim: str) -> str:
    value = payload.get(claim)
    if not isinstance(value, str) or not value:
        raise UnauthorizedError(f"Missing token claim: {claim}.")
    return value


def _required_int(payload: dict[str, Any], claim: str) -> int:
    value = payload.get(claim)
    if not isinstance(value, int):
        raise UnauthorizedError(f"Missing token claim: {claim}.")
    return value


def _audience_matches(value: Any, expected: str) -> bool:
    if isinstance(value, str):
        return value == expected
    if isinstance(value, list):
        return expected in value
    return False


def _scopes(payload: dict[str, Any]) -> tuple[str, ...]:
    scopes = payload.get("scopes", ())
    if isinstance(scopes, str):
        return tuple(scope for scope in scopes.split() if scope)
    if isinstance(scopes, list) and all(isinstance(scope, str) for scope in scopes):
        return tuple(scopes)
    return ()
