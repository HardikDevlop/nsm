# Daily Report — Page Summary

## Purpose

The Daily Report page is a read-only operational report for the previous 24 hours. It combines device availability, performance, interface activity, alerts, incidents, rankings, health observations, and recommendations into one report.

## Data source

- Frontend page: `figma design/src/pages/DailyReport.tsx`
- API call: `GET /reports/daily`
- Frontend API helper: `getDailyReport()` in `figma design/src/lib/api.ts`
- Data is generated from stored backend monitoring data; opening the page does not itself poll devices.

## Main page sections

1. **Device / Network Availability** — monitored device status and availability for the last 24 hours.
2. **Performance Monitoring** — metric sample count and performance indicators.
3. **Network Interface Details** — interface status, traffic, errors, and related port details.
4. **Alerts & Events** — alert summary for the last 24 hours.
5. **Incidents & Problems** — device status transitions and operational problems from the reporting window.
6. **Top Performers** — device rankings by CPU, memory, latency, downtime, and alert count.
7. **Daily Summary** — overall health, health score, availability percentage, issues, and devices needing attention.
8. **Recommendations** — suggested actions for Network / IT Operations.

## User actions

- Refresh the report by requesting the daily report endpoint again.
- Export the complete report to Excel (`.xlsx`).
- Review detailed tables and ranked device lists in the page sections.

## Excel export

The export includes report metadata, device/network availability, performance, interface details, alerts, incidents, top performers, daily summary, and recommendations. The filename format is:

`NMS_Daily_Report_<report-date>.xlsx`

## Time window

The report is fixed to the last 24 hours. It does not provide a custom date selector on the page.

## Operational interpretation

This page is intended for daily review and handoff: identify unavailable devices, degraded performance, interface issues, unresolved alerts, and recommended follow-up work.

## Important limitation

The report reflects persisted backend data available at generation time. Missing or stale monitoring data can make a section incomplete; the page should not be interpreted as a live device poll.
