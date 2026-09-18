# SNMP Interface Rate P0 Fix

Changed only the interface-rate calculation paths and their focused tests.

Old behavior: `counter_delta()` interpreted every decreasing counter as a 64-bit wrap, producing fabricated spikes when the counter had reset, changed width, or matched the wrong historical identity.

New behavior: interface rates use a dedicated monotonic guard. Missing counters, missing previous samples, non-positive elapsed time, and `current < previous` produce `NULL`. Increasing counters use the direct delta; equal counters produce genuine `0 Mbps`. Raw current cumulative counters continue to be written to `LatestInterface` and `InterfaceStatistic`, so a discontinuity establishes the next baseline and a following increasing sample recovers normally.

Known positive interface speed adds a conservative 10% directional tolerance: rates above `speed_bps / 1,000,000 * 1.10` are rejected as unavailable, never clamped. Unknown speed does not cause invented validation. Zero traffic remains valid.

The live API now uses canonical UTC helpers for elapsed-time arithmetic. Its utilization calculation requires both directional rates to be available, preventing a discontinuity from being treated as zero traffic. No display timezone behavior was changed.

`counter_delta()` itself remains unchanged for other consumers. No collector/OID, scheduler, Dashboard, ICMP, topology, alert behavior, historical DB rows, or transaction behavior was changed.

Tests cover increasing/equal/decreasing counters, recovery after a discontinuity, missing/invalid elapsed values, physical plausibility, UTC normalization, and no manual IST conversion. Python compile and focused checks were run; live device verification was not attempted.

COUNTER DECREASE PRODUCES WRAP SPIKE: NO
COUNTER DISCONTINUITY RATE: NULL
RAW COUNTERS STILL PERSIST: YES
NEXT VALID SAMPLE RECOVERS: YES
LIVE API ELAPSED UTC SAFE: YES
IMPOSSIBLE RATE CLAMPED: NO
IMPOSSIBLE RATE REJECTED AS NULL: YES
HISTORICAL DB ROWS MODIFIED: NO
SNMP COLLECTION SEMANTICS CHANGED: NO
FOCUSED TESTS: PASS
SAFE FOR REAL DEVICE RETEST: YES
