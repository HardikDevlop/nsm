from __future__ import annotations

import csv
import io

def spreadsheet_safe(value: object) -> object:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value

def generate_report_csv(rows: list[dict[str, object]]) -> bytes:
    prepared = []
    for row in rows:
        item = dict(row)
        if "downtime_seconds" in item:
            total = max(0, round(float(item.get("downtime_seconds") or 0)))
            days, remainder = divmod(total, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)
            item["downtime_seconds"] = f"{days}d {hours}h {minutes}m {seconds}s"
        prepared.append({key: spreadsheet_safe(value) for key, value in item.items()})
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(prepared[0].keys()) if prepared else ["device_id", "hostname"])
    writer.writeheader(); writer.writerows(prepared)
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")
