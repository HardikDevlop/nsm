from backend.services import realtime_monitor as rm
from datetime import datetime


def test_metric_batch_threshold_flushes_without_per_sample_commit(monkeypatch):
    engine = rm.MonitorEngine()
    flushed = []
    monkeypatch.setattr(engine, "_flush_metric_batch", lambda: flushed.append(True))
    for _ in range(rm.METRIC_BATCH_SIZE):
        engine._queue_metric(1, 1.0, 0.0, datetime.utcnow())
    assert flushed
    engine.shutdown()


def test_metric_batch_interval_is_bounded():
    assert rm.METRIC_BATCH_SIZE == 100
    assert rm.METRIC_BATCH_INTERVAL == 2.0
