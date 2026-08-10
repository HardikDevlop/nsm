"""Parser for common Linux and Windows ping output."""

from __future__ import annotations

import re
from typing import Any


def parse_ping_output(output: str, returncode: int) -> dict[str, Any]:
    text = output or ""
    reachable = returncode == 0
    loss_match = re.search(r"([\d.]+)%\s*(?:packet )?loss", text, re.I)
    loss = float(loss_match.group(1)) if loss_match else (0.0 if reachable else 100.0)
    rtts = [float(value) for value in re.findall(r"(?:time|Average|平均)\s*[=<]\s*([\d.]+)\s*ms", text, re.I)]
    avg_rtt = round(sum(rtts) / len(rtts), 2) if rtts else None
    ttl_match = re.search(r"ttl[=|:]([\d]+)", text, re.I)
    ttl = int(ttl_match.group(1)) if ttl_match else None
    return {
        "reachable": reachable,
        "packet_loss": round(loss, 2),
        "avg_rtt": avg_rtt,
        "ttl": ttl,
        "estimated_os": {"os": "Windows" if ttl and ttl <= 128 else "Unix/Linux"} if ttl else None,
        "hop_count": None,
    }
