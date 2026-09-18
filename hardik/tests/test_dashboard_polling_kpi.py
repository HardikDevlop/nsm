from datetime import datetime, timezone
from types import SimpleNamespace

from backend.api.overview_routes import _classify_polling_rows


def _row(status, stamp, row_id):
    return SimpleNamespace(
        id=row_id,
        status=status,
        created_at=datetime.fromtimestamp(stamp, tz=timezone.utc),
    )


def test_polling_kpis_keep_non_failure_outcomes_out_of_failure_rate():
    result = _classify_polling_rows([
        _row("success", 1, 1),
        _row("timeout", 2, 2),
        _row("not_supported", 3, 3),
        _row("no_data", 4, 4),
        _row("future_status", 5, 5),
    ])

    assert result["successful_attempts"] == 1
    assert result["failed_attempts"] == 1
    assert result["unsupported_attempts"] == 1
    assert result["no_data_attempts"] == 1
    assert result["unknown_attempts"] == 1
    assert result["total_attempts"] == 5
    assert result["success_rate"] == 0.5


def test_last_outcome_timestamps_are_deterministic_by_timestamp_then_id():
    result = _classify_polling_rows([
        _row("error", 10, 1),
        _row("error", 10, 2),
        _row("not_supported", 11, 3),
    ])

    assert result["last_failure"] == datetime.fromtimestamp(10, tz=timezone.utc).isoformat()
    assert result["last_unsupported"] == datetime.fromtimestamp(11, tz=timezone.utc).isoformat()


def test_no_eligible_attempts_have_null_success_rate():
    result = _classify_polling_rows([_row("no_data", 1, 1)])
    assert result["success_rate"] is None
