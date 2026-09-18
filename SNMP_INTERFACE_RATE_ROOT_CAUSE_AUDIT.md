# SNMP Interface Rate Root-Cause Audit

Scope: read-only audit of the Core-switch (`192.168.100.2`) interface-rate path. No application code or database data was changed.

## End-to-end path

The interface collector walks IF-MIB and ifXTable. `InterfaceCollector.collect()` prefers `hc_in_octets`/`hc_out_octets` when present and otherwise falls back to `in_octets`/`out_octets`. It emits the cumulative counters, `ifIndex`, interface name, speed, and status; collector utilization is explicitly `None` because a single sample cannot determine utilization.

The scheduler path is:

`SNMPService.collect_domain()` → `SNMPPoller.poll()` → `SNMPPoller._persist_results()` → `SNMPPoller._persist_interfaces()`.

The live device endpoint follows a second path: `_live_collect()` → `get_snmp_interfaces()`. It loads the persisted `LatestInterface` row by `device_id` and `if_index`, recalculates live rates from the current live counters versus that latest row, calculates utilization, calls `_persist_collect_result()`, and then returns the enriched response. `_persist_collect_result()` passes the interface collector payload to `_persist_results()` and commits it.

The persistence path writes raw cumulative counters to both `LatestInterface.rx_octets/tx_octets` and `InterfaceStatistic.rx_octets/tx_octets`, and writes calculated `rx_mbps`, `tx_mbps`, and quality fields to `InterfaceStatistic`. `LatestInterface` receives the calculated rates as well. The API response returns the live-enriched values, while other latest/history endpoints read the persisted values.

## Exact expressions

In `_persist_interfaces()`:

```python
in_oct = iface.get("in_octets") or iface.get("hc_in_octets")
out_oct = iface.get("out_octets") or iface.get("hc_out_octets")
prev = previous_by_id.get(iface_rec.id) or previous_by_id.get(if_index)
elapsed = _interface_elapsed_seconds(now, prev["created_at"])
rx_delta = counter_delta(float(in_oct or 0), float(prev["rx_octets"] or 0))
tx_delta = counter_delta(float(out_oct or 0), float(prev["tx_octets"] or 0))
rx_mbps = round(rx_delta * 8 / elapsed / 1_000_000, 3)
tx_mbps = round(tx_delta * 8 / elapsed / 1_000_000, 3)
```

The canonical time helper normalizes both operands as UTC before elapsed arithmetic. Missing previous timestamps use `60` seconds. Rates are only calculated when `elapsed > 0`; zero or negative elapsed values produce no rate.

The wrap/delta helper is:

```python
if current >= previous:
    return current - previous
return (2 ** bits - previous) + current
```

It defaults to a 64-bit counter, regardless of whether the source sample was actually 32-bit.

In `get_snmp_interfaces()`, the live response has a separate calculation:

```python
elapsed = max((now - latest.polled_at).total_seconds(), 0)
rx_mbps = round(counter_delta(float(in_octets), float(latest.rx_octets)) * 8 / elapsed / 1_000_000, 3)
tx_mbps = round(counter_delta(float(out_octets), float(latest.tx_octets)) * 8 / elapsed / 1_000_000, 3)
utilization = round(((rx_mbps or 0) + (tx_mbps or 0)) * 1_000_000 / float(speed_bps) * 100, 2)
```

That endpoint uses `datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)` and compares it with the DB-derived `LatestInterface.polled_at`; this is a separate API-time arithmetic risk from the already-fixed persistence crash and is relevant when interpreting live HTTP values.

## Previous-row selection

`_load_latest_interface_statistics()` uses a window function partitioned by `InterfaceStatistic.interface_id`, ordered by:

```python
InterfaceStatistic.created_at.desc(), InterfaceStatistic.id.desc()
```

It filters by the same `device_id` and a set containing current legacy interface IDs plus ifIndexes. Therefore selection is deterministic for each `interface_id`, including an ID tie-breaker. The query runs before the current persistence loop adds its new `InterfaceStatistic` rows, so a row written during that same `_persist_interfaces()` invocation cannot become the previous row. Duplicate input records in one payload also do not alter the already-loaded previous-row map.

The identity path is not perfectly uniform: the primary lookup is `previous_by_id.get(iface_rec.id)`, while the fallback is `previous_by_id.get(if_index)` for legacy rows. The fallback is intentional compatibility for historical rows written before interface foreign keys were consistently used. It is safe only when the legacy `interface_id` value represents that same physical ifIndex; the query itself cannot prove that relationship. Interface-name matching is used to resolve the current `Interface` row, and can also be vulnerable to historical renaming/re-identification if names are reused.

## Counter audit

- The collector prefers 64-bit ifXTable high-capacity octets and falls back to 32-bit IF-MIB octets.
- Persistence does not record which width supplied each counter.
- `counter_delta()` always uses 64-bit wrap arithmetic by default.
- A current counter lower than the previous counter is therefore interpreted as a 64-bit wrap, even when it represents a reset, reboot, interface replacement, bad identity match, or a 32-bit wrap.
- There is no explicit reset/reboot detection, counter-width detection, interface incarnation detection, or rejection of implausible deltas in this path.
- Raw cumulative octets, not previous `rx_mbps`/`tx_mbps`, feed future deltas. Historical bad rate values do not directly feed future counter calculations.

## Elapsed audit and mathematical explanation

For a repeated value `R = 826,900,154 Mbps`, the rate formula implies:

```text
R = delta_octets × 8 / elapsed_seconds / 1,000,000
```

When `current < previous`, the current code uses:

```text
delta_octets = 2^64 - previous + current
```

The dominant wrap term gives:

```text
elapsed ≈ 2^64 × 8 / (826,900,154 × 1,000,000)
         ≈ 178,466.47 seconds
         ≈ 49.57 hours
```

Thus the repeated value is numerically consistent with a 64-bit wrap/reset-style branch combined with an old or mismatched previous counter and an elapsed interval around 49.6 hours. The exact value can differ slightly because `previous` and `current` are included in the wrap expression and because the result is rounded to three decimals. This is a code-semantic explanation, not a claim that the device actually wrapped a 64-bit counter.

There is no evidence in this path that timezone normalization itself creates a tiny positive elapsed value: the audited persistence helper converts both timestamps to UTC. A very small positive elapsed would amplify an ordinary delta, but it would not explain the repeated value as directly as the 64-bit wrap term above. Old duplicate-backend rows can affect the selected previous sample if they remain the newest row for the same identity; same-cycle selection is not the cause.

## Units and utilization

The collector values are octets. The rate calculation multiplies octets by 8 to obtain bits, divides by seconds, then divides by 1,000,000 to produce Mbps. `speed_bps` is bits per second. This conversion is dimensionally correct.

The API utilization formula is:

```text
((rx_mbps + tx_mbps) × 1,000,000 / speed_bps) × 100
```

It sums RX and TX, then divides by interface speed. For a 1 Gbps interface, 1,000 Mbps in one direction corresponds to approximately 100% utilization; 1,000 Mbps RX plus 1,000 Mbps TX corresponds to approximately 200% under this aggregate-bidirectional convention. The persistence function stores collector-provided utilization, which is currently `None` from this collector; the live interface API computes the summed utilization shown above.

## Findings

The primary root cause is unsafe interpretation of every decreasing counter as a 64-bit wrap, combined with a previous raw counter that may be stale, reset-era, width-mismatched, or identity-mismatched. The ~826,900,154 Mbps repetition quantitatively matches the 64-bit wrap term over an approximately 49.6-hour elapsed interval.

Secondary causes/risk factors are: no counter-width metadata or 32-bit-specific wrap handling; no reset/reboot or interface-incarnation detection; legacy ifIndex fallback that is not independently identity-verified; possible polluted historical rows from prior duplicate-backend periods; and a separate live API elapsed calculation using naive local-IST wall time against DB timestamps. The latter can distort live rates but is not needed to explain the repeated persisted value.

The safe minimal fix should be designed after runtime evidence confirms the selected previous row, its raw counters, its timestamp, counter source/width, and the current sample. It should reject or mark reset/identity changes as unavailable rather than automatically applying wrap math without evidence. No fix was implemented in this audit.

EXACT RATE FORMULA: `counter_delta(current_octets, previous_octets) * 8 / elapsed_seconds / 1,000,000`
PREVIOUS SAMPLE SELECTION: Deterministic per `interface_id`, `created_at DESC, id DESC`; device-filtered, with legacy ifIndex fallback
ELAPSED VALUE RISK: Old/mismatched timestamps can distort rates; current persistence normalization is UTC-safe, while the live API has a separate naive-local-time risk
COUNTER RESET/WRAP HANDLING: Any decrease is treated as 64-bit wrap; no reset/reboot/width detection
SAME-CYCLE PREVIOUS-ROW RISK: NO
UNIT CONVERSION CORRECT: YES
UTILIZATION FORMULA: `((rx_mbps + tx_mbps) * 1,000,000 / speed_bps) * 100` in the live API; aggregate RX+TX
WHY ~826900154 Mbps OCCURS: A decreasing counter enters the 64-bit wrap branch; the 2^64 term divided by roughly 178,466 seconds produces approximately 826,900,154 Mbps
PRIMARY ROOT CAUSE: Unvalidated 64-bit wrap interpretation of a reset, stale, width-mismatched, or identity-mismatched previous counter
SECONDARY ROOT CAUSES: Legacy ifIndex identity fallback, polluted historical rows, no counter-width/incarnation metadata, and separate live API timezone/elapsed risk
HISTORICAL BAD RATE VALUES AFFECT FUTURE DELTAS: NO
SAFE MINIMAL FIX: Validate previous-row identity/timestamp/counter continuity and treat reset/invalid or implausible deltas as unavailable before applying wrap math
CODE CHANGED: NO
