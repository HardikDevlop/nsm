"""
Unit tests for CollectorResponse and BaseCollector contracts.
"""

import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.snmp.collectors.base import (
    CollectorResponse,
    CollectorResult,
    BaseCollector,
    _safe_num,
    _safe_str,
    _safe_mac,
    _find_in_raw,
    _get_oid,
)


class TestCollectorResponse:

    def test_ok_response_fields(self):
        resp = CollectorResponse.ok("cpu", {"overall_percent": 42.0})
        assert resp.supported is True
        assert resp.collector == "cpu"
        assert resp.data["overall_percent"] == 42.0
        assert resp.reason is None
        assert isinstance(resp.timestamp, str)

    def test_unsupported_response_fields(self):
        resp = CollectorResponse.unsupported(
            "cpu", reason="hrProcessorLoad OID not found", missing=["hrProcessorLoad"]
        )
        assert resp.supported is False
        assert resp.reason == "hrProcessorLoad OID not found"
        assert "hrProcessorLoad" in resp.missing
        assert resp.data == {}

    def test_ok_never_contains_not_supported_string(self):
        resp = CollectorResponse.ok("memory", {"total_bytes": None})
        assert "Not Supported" not in str(resp.data.values())

    def test_to_dict_supported(self):
        resp = CollectorResponse.ok("cpu", {"overall_percent": 55.0}, warnings=["high load"])
        d = resp.to_dict()
        assert d["supported"] is True
        assert "data" in d
        assert "warnings" in d
        assert "reason" not in d

    def test_to_dict_unsupported(self):
        resp = CollectorResponse.unsupported("cpu", reason="no OID")
        d = resp.to_dict()
        assert d["supported"] is False
        assert "reason" in d
        assert "data" not in d

    def test_missing_defaults_to_empty_list(self):
        resp = CollectorResponse.ok("test", {})
        assert resp.missing == []

    def test_warnings_defaults_to_empty_list(self):
        resp = CollectorResponse.ok("test", {})
        assert resp.warnings == []


class TestCollectorResultLegacy:
    """Legacy CollectorResult shim must still work."""

    def test_basic_construction(self):
        result = CollectorResult("cpu", {"utilization": 42}, ["missing_key"])
        assert result.collector == "cpu"
        assert result.data["utilization"] == 42
        assert "missing_key" in result.unsupported

    def test_json_method(self):
        result = CollectorResult("memory", {"total": 1024})
        j = result.json()
        assert j["collector"] == "memory"
        assert "data" in j

    def test_from_response_supported(self):
        resp = CollectorResponse.ok("cpu", {"val": 10}, missing=["x"])
        result = CollectorResult.from_response(resp)
        assert result.collector == "cpu"
        assert result.data == {"val": 10}

    def test_from_response_unsupported(self):
        resp = CollectorResponse.unsupported("cpu", "no OID")
        result = CollectorResult.from_response(resp)
        assert result.data["supported"] is False
        assert "reason" in result.data


class TestBaseCollectorHelpers:

    class _Collector(BaseCollector):
        name = "test"
        def collect(self, raw, oid_registry=None, vendor_profile=None):
            return CollectorResponse.ok(self.name, {})

    def setup_method(self):
        self.c = self._Collector()

    def test_num_int(self):
        assert self.c.num("42") == 42
        assert self.c.num(3.14) == 3.14

    def test_num_none_on_garbage(self):
        assert self.c.num("N/A") is None
        assert self.c.num(None) is None

    def test_text_clean_string(self):
        assert self.c.text("hello") == "hello"

    def test_text_none_on_empty(self):
        assert self.c.text("") is None
        assert self.c.text("N/A") is None
        assert self.c.text("noSuchObject") is None

    def test_mac_normalization(self):
        assert self.c.mac("001122334455") == "00:11:22:33:44:55"
        assert self.c.mac(None) is None

    def test_percent_calculation(self):
        assert self.c.percent(40, 100) == 40.0
        assert self.c.percent(1, 3) == pytest.approx(33.33, abs=0.01)
        assert self.c.percent(None, 100) is None
        assert self.c.percent(50, 0) is None

    def test_oid_last(self):
        assert self.c.oid_last("1.3.6.1.2.1.1.5.1") == "1"
        assert self.c.oid_last("1.3.6.1.2.1.1.5.1", 2) == "5.1"

    def test_find_returns_subtree(self):
        raw = {
            "1.3.6.1.2.1.2.2.1.2.1": "eth0",
            "1.3.6.1.2.1.2.2.1.2.2": "eth1",
            "1.3.6.1.2.1.1.5.0":      "router01",
        }
        result = self.c.find(raw, "1.3.6.1.2.1.2.2.1.2")
        assert "1" in result
        assert "2" in result
        assert len(result) == 2

    def test_get_with_dot0_fallback(self):
        raw = {"1.3.6.1.2.1.1.5.0": "router01"}
        # Exact match with .0
        assert self.c.get(raw, "1.3.6.1.2.1.1.5.0") == "router01"
        # Without .0 — get() appends .0 as fallback, so this DOES find it
        assert self.c.get(raw, "1.3.6.1.2.1.1.5") == "router01"
        # Completely unknown OID returns None
        assert self.c.get(raw, "9.9.9.9.9") is None

    def test_probe_adds_to_missing(self):
        raw = {}
        missing = []
        result = self.c.probe(raw, "1.2.3.4.5.0", missing, label="cpu.overall")
        assert result is None
        assert "cpu.overall" in missing

    def test_warn_appends_message(self):
        warnings = []
        self.c.warn(warnings, "high temperature")
        assert "high temperature" in warnings


class TestStaticHelpers:
    def test_safe_num_various(self):
        assert _safe_num(0) == 0
        assert _safe_num("0.5") == 0.5
        assert _safe_num("1,234") == 1234
        assert _safe_num("abc") is None

    def test_safe_str_filters_bad_values(self):
        assert _safe_str("hello") == "hello"
        assert _safe_str("") is None
        assert _safe_str("noSuchObject") is None
        assert _safe_str("No Such Instance") is None

    def test_safe_mac_formats(self):
        assert _safe_mac("aabbccddeeff") == "AA:BB:CC:DD:EE:FF"
        assert _safe_mac("aa:bb:cc:dd:ee:ff") == "AA:BB:CC:DD:EE:FF"
        assert _safe_mac("0xAABBCCDDEEFF") == "AA:BB:CC:DD:EE:FF"
        assert _safe_mac("short") is None

    def test_find_in_raw_prefix(self):
        raw = {
            "1.2.3.4.1": "a",
            "1.2.3.4.2": "b",
            "1.2.3.5.1": "c",
        }
        result = _find_in_raw(raw, "1.2.3.4")
        assert result == {"1": "a", "2": "b"}

    def test_get_oid_exact_and_fallback(self):
        raw = {"1.2.3.0": "val"}
        assert _get_oid(raw, "1.2.3.0") == "val"
        assert _get_oid(raw, "9.9.9") is None
