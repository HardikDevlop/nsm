import asyncio

from tools.nms_loadtest import NMSLoadRunner, Sample, SimulatedSNMPWorkload, WorkloadResult


def test_percentiles_and_throughput_are_computed_from_samples():
    result = WorkloadResult.from_samples(
        "api", [
            Sample(value, True, 200)
            for value in (10, 20, 30, 40, 50)
        ], 1.0,
    )
    assert result.requests == 5
    assert result.successes == 5
    assert result.p50_ms == 30
    assert result.p95_ms == 50
    assert result.p99_ms == 50
    assert result.throughput_rps == 5.0


def test_simulated_snmp_workload_is_bounded_and_reports_failures():
    workload = SimulatedSNMPWorkload(operation_ms=0, failure_rate=1.0, workers=2)
    result = asyncio.run(workload.run(8))
    assert result.requests == 8
    assert result.successes == 0
    assert result.failures == 8


def test_api_load_runner_uses_real_request_boundary(monkeypatch):
    runner = NMSLoadRunner("http://nms.test", token="token")
    calls = []
    async def direct_to_thread(function, *args):
        return function(*args)

    monkeypatch.setattr("asyncio.to_thread", direct_to_thread)
    monkeypatch.setattr(runner, "request", lambda path: calls.append(path) or Sample(1, True, 200))
    result = asyncio.run(runner.run_api("api", ["/health", "/api/v1/devices"], 4, 2))
    assert result.requests == 4
    assert set(calls) == {"/health", "/api/v1/devices"}
