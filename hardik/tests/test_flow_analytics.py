from datetime import datetime

from backend.api.flow_routes import _analytics, _where


class _Result:
    def mappings(self):
        return self

    def all(self):
        return [{"name": "10.0.0.1", "bytes": 100, "packets": 2, "flows": 1}]


class _Db:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return _Result()


def test_flow_analytics_uses_one_parameterized_aggregate_query_and_pagination():
    db = _Db()
    result = _analytics("talkers", 24, 7, 3, 25, 2, db)
    assert result["items"][0]["bytes"] == 100
    assert len(db.calls) == 1
    sql, params = db.calls[0]
    assert "GROUP BY" in sql and "SUM(f.bytes)" in sql
    assert params["device_id"] == 7 and params["site_id"] == 3
    assert (params["limit"], params["offset"]) == (25, 25)


def test_flow_filter_window_is_bounded():
    start = datetime(2026, 1, 1)
    end = datetime(2026, 1, 2)
    where, params = _where(None, None, start, end)
    assert "f.flow_start >= :start" in where and "f.flow_start < :end" in where
    assert params == {"start": start, "end": end}
