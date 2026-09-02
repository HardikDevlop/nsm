from datetime import datetime

import pytest

from backend.apm.service import APMMetric, MAX_BATCH_SIZE, cleanup_metrics, ingest_metrics, metric_values
from backend.api.apm_routes import APMMetricBatch, APMMetricPayload, _filters, router


class FakeDB:
    def __init__(self):
        self.calls = []
        self.commits = 0

    def execute(self, statement, params):
        self.calls.append((str(statement), params))

    def commit(self):
        self.commits += 1


class DeleteResult:
    rowcount = 2


def metric(**overrides):
    values = {
        "application_id": 1,
        "service_id": 2,
        "observed_at": datetime(2026, 8, 29, 10, 0),
        "response_time_ms": 125.5,
        "request_count": 20,
        "error_count": 2,
        "slow_transaction_count": 3,
        "availability_percent": 99.5,
    }
    values.update(overrides)
    return APMMetric(**values)


def test_metric_validation_and_hash_are_deterministic():
    first = metric()
    second = metric()
    first.validate()
    assert first.record_hash == second.record_hash
    assert metric_values(first, datetime(2026, 8, 29, 10, 1))["record_hash"] == first.record_hash


@pytest.mark.parametrize("overrides", [
    {"response_time_ms": -1},
    {"request_count": 1, "error_count": 2},
    {"availability_percent": 101},
])
def test_metric_rejects_invalid_values(overrides):
    with pytest.raises(ValueError):
        metric(**overrides).validate()


def test_ingestion_uses_one_bulk_insert_and_one_commit():
    db = FakeDB()
    accepted = ingest_metrics(db, [metric(), metric(observed_at=datetime(2026, 8, 29, 10, 1))], datetime.utcnow())
    assert accepted == 2
    assert len(db.calls) == 1
    assert len(db.calls[0][1]) == 2
    assert "ON CONFLICT (record_hash) DO NOTHING" in db.calls[0][0]
    assert db.commits == 1


def test_ingestion_has_a_hard_batch_limit():
    with pytest.raises(ValueError, match="maximum APM metric batch size"):
        ingest_metrics(FakeDB(), [metric() for _ in range(MAX_BATCH_SIZE + 1)], datetime.utcnow())


def test_api_payload_batch_is_bounded_and_typed():
    payload = APMMetricPayload(
        application_id=1,
        service_id=2,
        observed_at="2026-08-29T10:00:00Z",
        response_time_ms=10,
        request_count=1,
        error_count=0,
    )
    batch = APMMetricBatch(metrics=[payload])
    assert batch.metrics[0].availability_percent == 100


def test_time_window_filters_are_parameterized():
    start = datetime(2026, 8, 29, 9, 0)
    end = datetime(2026, 8, 29, 10, 0)
    where, params = _filters(7, 3, 11, 13, start, end)
    assert "m.observed_at >= :start" in where
    assert "m.observed_at < :end" in where
    assert params == {"start": start, "end": end, "device_id": 7, "site_id": 3, "application_id": 11, "service_id": 13}


def test_retention_uses_bounded_delete_batches():
    class RetentionDB(FakeDB):
        def execute(self, statement, params):
            self.calls.append((str(statement), params))
            return DeleteResult()

    db = RetentionDB()
    assert cleanup_metrics(db, datetime(2026, 1, 1), batch_size=10_000) == 2
    assert len(db.calls) == 1
    assert "DELETE FROM apm_metric_samples" in db.calls[0][0]
    assert db.commits == 1


def test_apm_router_exposes_ingest_query_and_retention_contracts():
    paths = {route.path for route in router.routes}
    assert paths == {
        "/api/v1/apm/metrics",
        "/api/v1/apm/applications",
        "/api/v1/apm/services",
        "/api/v1/apm/overview",
        "/api/v1/apm/services/{service_id}/metrics",
        "/api/v1/apm/dependencies",
        "/api/v1/apm/retention/run",
    }
