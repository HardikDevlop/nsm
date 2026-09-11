# ICMP Step 5 Reusable Probe Report

## Probe model

Before, every realtime sample called `subprocess.run(["ping", "-c", "1", "-W", "1", ip], timeout=3.0)` on Linux. Success required return code zero and `ttl=` in stdout; RTT was parsed from `time=...`; timeout/OSError returned `(False, None)`.

After, the bounded Step 2 monitor executor invokes a native one-packet raw ICMP probe first. It creates an isolated socket per probe (no shared mutable socket), waits up to the same 1,000 ms probe timeout, validates an echo reply and nonzero IP TTL, and returns the measured RTT. Raw-socket permission/platform failures are classified as engine-unavailable and switch to the unchanged subprocess helper. A remote timeout returns unreachable and does not switch engines. The subprocess fallback retains the original command, parsing, three-second subprocess deadline, and failure behavior.

## Runtime/test evidence

Focused reusable-probe, executor, and batching tests: **8 passed**. Compilation passed. Live raw-socket/device verification is pending because the Codex runtime cannot establish live network access; no system capabilities were changed.

