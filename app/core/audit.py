from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    tenant_id: str
    project_id: str
    job_id: str
    created_at: datetime
    metadata: dict[str, Any]


class AuditRecorder:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, *, event_type: str, tenant_id: str, project_id: str, job_id: str, **metadata: Any) -> None:
        event = AuditEvent(
            event_type=event_type,
            tenant_id=tenant_id,
            project_id=project_id,
            job_id=job_id,
            created_at=datetime.now(UTC),
            metadata=metadata,
        )
        self.events.append(event)
        logger.info(
            "audit event recorded",
            extra={
                "event_type": event_type,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "job_id": job_id,
            },
        )
