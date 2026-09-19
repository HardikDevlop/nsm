# Report Management — Page Summary

## Purpose

Report Management is an interactive reporting workspace for generating, reviewing, filtering, and exporting availability and performance reports across devices.

## Data source

- Frontend page: `figma design/src/pages/ReportManagement.tsx`
- Report API: `GET /reports/management`
- Filter options API: `GET /reports/management/options`
- CSV export API: `GET /reports/management/export?format=csv`
- Frontend API helpers are in `figma design/src/lib/api.ts`.

## Filters

- Device type
- Individual device
- Site
- Protocol: SNMP + ICMP, SNMP, or ICMP
- Period: weekly, monthly, yearly, or custom date range
- Custom start and end dates when the custom period is selected

Changing filters updates the local form state. **Run Report** sends the selected filters to the backend and refreshes the results.

## Summary metrics

The page displays:

- Availability percentage
- Total downtime in seconds
- Average SNMP health
- SLA-met percentage
- Additional performance and device totals returned by the backend

## Report sections

The backend summary is grouped into sections such as:

- Availability
- Downtime
- SNMP Health
- Interface / Port
- Performance
- SLA Summary

Each section can include record count, average, maximum, and minimum values where applicable.

## Device-level report table

Each row can include:

- Device name, IP address, site, and device type
- Protocol used
- Availability and downtime
- SNMP success rate and ICMP success rate
- SNMP health and performance score
- Interface count and interfaces down
- Average CPU and memory
- Average latency and packet loss
- SLA status
- Report period start and end

## Export options

### CSV

CSV is downloaded from the backend export endpoint using the currently selected filters.

### Excel

Excel is generated in the browser using the `xlsx` package. It contains:

- `Reports` sheet with device-level records
- `Summary` sheet with period, device count, availability, downtime, and SLA metrics

Export filenames use:

`report-management-<start-date>-<end-date>.<csv|xlsx>`

## Data behavior

- The initial page load uses the default weekly period and loads filter options plus a report summary.
- The page uses real stored SNMP and ICMP data; it does not claim to create live polling jobs.
- Device selection is narrowed by the selected device type and site.
- Export actions use the currently generated summary/filter state.

## Operational interpretation

Use this page for selectable-period reporting, SLA review, device comparison, and sharing data with operations or management teams. Use Daily Report for a fixed daily operational snapshot.

## Important limitation

Changing a filter does not automatically run the report; the user must click **Run Report**. If the backend has no stored data for the selected period or protocol, metrics may be empty or unavailable.
