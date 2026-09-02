from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, Iterable

from sqlalchemy import text


MAX_BATCH_SIZE = 500


@dataclass(frozen=True, slots=True)
class APMMetric:
    application_id: int
    service_id: int
    observed_at: datetime
    response_time_ms: float
    request_count: int
    error_count: int
    slow_transaction_count: int
    availability_percent: float
    transaction_id: int | None = None
    device_id: int | None = None
    site_id: int | None = None

    @property
    def record_hash(self) -> str:
        values = (
            self.application_id, self.service_id, self.transaction_id,
            self.observed_at.isoformat(), self.response_time_ms,
            self.request_count, self.error_count, self.slow_transaction_count,
            self.availability_percent,
        )
        return sha256("|".join(map(str, values)).encode("utf-8")).hexdigest()

    def validate(self) -> None:
        if self.application_id <= 0 or self.service_id <= 0:
            raise ValueError("application_id and service_id must be positive")
        if self.response_time_ms < 0:
            raise ValueError("response_time_ms cannot be negative")
        if self.request_count < 0 or self.error_count < 0 or self.slow_transaction_count < 0:
            raise ValueError("metric counts cannot be negative")
        if self.error_count > self.request_count:
            raise ValueError("error_count cannot exceed request_count")
        if not 0 <= self.availability_percent <= 100:
            raise ValueError("availability_percent must be between 0 and 100")


INSERT_METRICS = text("""
    INSERT INTO apm_metric_samples
      (application_id, service_id, transaction_id, device_id, site_id, observed_at,
       response_time_ms, request_count, error_count, slow_transaction_count,
       availability_percent, record_hash, created_at)
    VALUES (:application_id, :service_id, :transaction_id, :device_id, :site_id,
      :observed_at, :response_time_ms, :request_count, :error_count,
      :slow_transaction_count, :availability_percent, :record_hash, :created_at)
    ON CONFLICT (record_hash) DO NOTHING
""")

DELETE_METRICS_BATCH = text("""
    DELETE FROM apm_metric_samples
    WHERE id IN (
        SELECT id FROM apm_metric_samples
        WHERE observed_at < :cutoff
        ORDER BY id
        LIMIT :batch_size
    )
""")


def metric_values(metric: APMMetric, created_at: datetime) -> dict[str, Any]:
    metric.validate()
    return {
        "application_id": metric.application_id,
        "service_id": metric.service_id,
        "transaction_id": metric.transaction_id,
        "device_id": metric.device_id,
        "site_id": metric.site_id,
        "observed_at": metric.observed_at,
        "response_time_ms": metric.response_time_ms,
        "request_count": metric.request_count,
        "error_count": metric.error_count,
        "slow_transaction_count": metric.slow_transaction_count,
        "availability_percent": metric.availability_percent,
        "record_hash": metric.record_hash,
        "created_at": created_at,
    }


def ingest_metrics(db: Any, metrics: Iterable[APMMetric], created_at: datetime) -> int:
    batch = list(metrics)
    if not batch:
        return 0
    if len(batch) > MAX_BATCH_SIZE:
        raise ValueError(f"maximum APM metric batch size is {MAX_BATCH_SIZE}")
    db.execute(INSERT_METRICS, [metric_values(metric, created_at) for metric in batch])
    db.commit()
    return len(batch)


def cleanup_metrics(db: Any, cutoff: datetime, batch_size: int = 1000) -> int:
    """Delete old samples in bounded transactions to avoid long retention locks."""
    if batch_size < 1 or batch_size > 10_000:
        raise ValueError("batch_size must be between 1 and 10000")
    deleted = 0
    while True:
        result = db.execute(DELETE_METRICS_BATCH, {"cutoff": cutoff, "batch_size": batch_size})
        count = result.rowcount or 0
        db.commit()
        deleted += count
        if count < batch_size:
            return deleted
