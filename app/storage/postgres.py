from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.errors import InvalidStateTransitionError, NotFoundError
from app.domain.models import EvaluationJob, EvaluationResult, JobStatus


class Base(DeclarativeBase):
    pass


class EvaluationJobRow(Base):
    __tablename__ = "evaluation_jobs"

    job_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PostgresJobRepository:
    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)
        self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)

    async def init_schema(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self._engine.dispose()

    async def create(self, job: EvaluationJob) -> EvaluationJob:
        async with self._sessionmaker() as session:
            session.add(self._to_row(job))
            await session.commit()
        return job

    async def get(self, job_id: UUID) -> EvaluationJob:
        async with self._sessionmaker() as session:
            row = await session.get(EvaluationJobRow, job_id)
            if row is None:
                raise NotFoundError()
            return self._to_domain(row)

    async def set_running(self, job_id: UUID) -> EvaluationJob:
        return await self._transition(job_id, {JobStatus.QUEUED}, JobStatus.RUNNING)

    async def set_succeeded(self, job_id: UUID, result: EvaluationResult) -> EvaluationJob:
        async with self._sessionmaker() as session:
            row = await session.get(EvaluationJobRow, job_id, with_for_update=True)
            if row is None:
                raise NotFoundError()
            self._validate_transition(row.status, {JobStatus.RUNNING})
            row.status = JobStatus.SUCCEEDED.value
            row.result_payload = result.model_dump()
            row.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(row)
            return self._to_domain(row)

    async def set_failed(self, job_id: UUID, message: str) -> EvaluationJob:
        async with self._sessionmaker() as session:
            row = await session.get(EvaluationJobRow, job_id, with_for_update=True)
            if row is None:
                raise NotFoundError()
            self._validate_transition(row.status, {JobStatus.QUEUED, JobStatus.RUNNING})
            row.status = JobStatus.FAILED.value
            row.error_message = message
            row.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(row)
            return self._to_domain(row)

    async def _transition(
        self,
        job_id: UUID,
        allowed_from: set[JobStatus],
        target: JobStatus,
    ) -> EvaluationJob:
        async with self._sessionmaker() as session:
            row = await session.get(EvaluationJobRow, job_id, with_for_update=True)
            if row is None:
                raise NotFoundError()
            self._validate_transition(row.status, allowed_from)
            row.status = target.value
            row.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(row)
            return self._to_domain(row)

    @staticmethod
    def _validate_transition(current_status: str, allowed_from: set[JobStatus]) -> None:
        current = JobStatus(current_status)
        if current not in allowed_from:
            raise InvalidStateTransitionError()

    @staticmethod
    def _to_row(job: EvaluationJob) -> EvaluationJobRow:
        return EvaluationJobRow(
            job_id=job.job_id,
            tenant_id=job.tenant_id,
            project_id=job.project_id,
            status=JobStatus(job.status).value,
            request_payload=job.request.model_dump(),
            result_payload=job.result.model_dump() if job.result else None,
            error_message=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    @staticmethod
    def _to_domain(row: EvaluationJobRow) -> EvaluationJob:
        return EvaluationJob(
            job_id=row.job_id,
            tenant_id=row.tenant_id,
            project_id=row.project_id,
            status=JobStatus(row.status),
            request=row.request_payload,
            result=row.result_payload,
            error_message=row.error_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
