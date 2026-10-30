from datetime import datetime

from backend.services.report_pdf import generate_report_pdf


def test_pdf_contains_title_period_headers_and_values():
    content = generate_report_pdf(
        [{"hostname": "router-1", "site": "HQ", "availability": "99.5%"}],
        title="Management Report",
        period_start=datetime(2026, 1, 1),
        period_end=datetime(2026, 2, 1),
    )
    assert content.startswith(b"%PDF-")
    assert len(content) > 1000
    assert b"Management Report" in content
    assert b"Period:" in content
    assert b"router-1" in content
    assert b"availability" in content


def test_pdf_handles_empty_rows():
    content = generate_report_pdf([], title="Empty Report")
    assert content.startswith(b"%PDF-")
    assert b"Empty Report" in content
    assert b"device_id" in content
    assert b"hostname" in content


def test_pdf_paginates_large_reports_and_handles_special_long_values():
    rows = [{"hostname": f"router-{index}", "description": "Café & core <edge> " + ("long-value " * 30)} for index in range(120)]
    content = generate_report_pdf(rows, title="Large & Detailed Report", period_start="2026-01-01", period_end="2026-01-31")
    assert content.startswith(b"%PDF-")
    assert content.count(b"/Type /Page") > 1
    assert len(content) > 10_000
    assert b"router-119" in content

