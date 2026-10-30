from __future__ import annotations

from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger

from backend.database.session import SessionLocal
from backend.auth.authorization import can_access_site, get_accessible_site_ids, is_super_admin
from backend.models import Device, GeneratedReport, ReportSchedule, User
from backend.schemas.nms import ReportManagementFilters
from backend.services.report_management import build_report_rows
from backend.services.report_csv import generate_report_csv
from backend.services.report_pdf import generate_report_pdf
from backend.services.report_xlsx import generate_report_xlsx

logger = logging.getLogger(__name__)
JOB_PREFIX = "report_schedule_"
REPORT_STORAGE_DIR = Path(os.getenv("NMS_REPORT_STORAGE_DIR", "runtime/generated_reports")).resolve()
_scheduler = None


class ReportScheduleAuthorizationError(ValueError):
    """Safe, non-sensitive failure raised when a schedule is no longer valid."""


def _authorize_schedule_execution(db, schedule: ReportSchedule) -> None:
    """Validate creator status and persisted scope before scheduled execution."""
    if schedule.created_by is None:
        raise ReportScheduleAuthorizationError("schedule creator is unavailable")
    creator = db.query(User).filter(User.id == schedule.created_by).first()
    if creator is None or creator.status != "active":
        raise ReportScheduleAuthorizationError("schedule creator is inactive")

    try:
        filters = ReportManagementFilters(**dict(schedule.filters or {})).model_dump()
    except Exception as exc:
        raise ReportScheduleAuthorizationError("schedule scope is invalid") from exc
    site_id = filters.get("site_id")
    device_id = filters.get("device_id")
    accessible_site_ids = get_accessible_site_ids(creator)
    if is_super_admin(creator):
        return
    if accessible_site_ids is None or site_id is None and device_id is None:
        raise ReportScheduleAuthorizationError("schedule scope is invalid")
    if site_id is not None and not can_access_site(creator, site_id):
        raise ReportScheduleAuthorizationError("schedule scope is unauthorized")
    if device_id is not None:
        device = db.query(Device).filter(Device.id == device_id, Device.deleted_at.is_(None)).first()
        if device is None or not can_access_site(creator, device.site_id):
            raise ReportScheduleAuthorizationError("schedule scope is unauthorized")
        if site_id is not None and device.site_id != site_id:
            raise ReportScheduleAuthorizationError("schedule scope is invalid")


def set_report_scheduler(polling_scheduler: object | None) -> None:
    global _scheduler
    _scheduler = getattr(polling_scheduler, "scheduler", None)


def _tz(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "Asia/Kolkata")
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Kolkata")


def schedule_job_id(schedule_id: int) -> str:
    return f"{JOB_PREFIX}{schedule_id}"


def _sync_next_run_at(schedule: ReportSchedule) -> None:
    """Copy the current report job's next run time, when available."""
    if _scheduler is None:
        return
    try:
        job = _scheduler.get_job(schedule_job_id(schedule.id))
        next_run_time = getattr(job, "next_run_time", None) if job is not None else None
        schedule.next_run_at = (
            next_run_time.astimezone(_tz(schedule.timezone)).replace(tzinfo=None)
            if next_run_time is not None else None
        )
    except Exception:
        logger.debug("Unable to synchronize next run time for report schedule %s", schedule.id, exc_info=True)


def _window(schedule: ReportSchedule, now: datetime | None = None) -> tuple[datetime, datetime]:
    zone = _tz(schedule.timezone)
    current = (now or datetime.now(zone)).astimezone(zone)
    today = current.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    if schedule.frequency == "daily":
        return today - timedelta(days=1), today
    if schedule.frequency == "weekly":
        return today - timedelta(days=7), today
    first = today.replace(day=1)
    previous_month = first - timedelta(days=1)
    previous_first = previous_month.replace(day=1)
    return previous_first, first


def _run_schedule(schedule_id: int) -> None:
    with SessionLocal() as db:
        schedule = db.query(ReportSchedule).filter(ReportSchedule.id == schedule_id).first()
        if schedule is None or not schedule.enabled:
            return
        start, end = _window(schedule)
        report_name = schedule.name
        report_format = getattr(schedule, "report_format", None) or "csv"
        generated = GeneratedReport(schedule_id=schedule.id, report_name=report_name, format=report_format, status="RUNNING", period_start=start, period_end=end, generated_at=datetime.now(_tz(schedule.timezone)))
        db.add(generated); db.commit(); db.refresh(generated)
        temp_path: Path | None = None
        try:
            _authorize_schedule_execution(db, schedule)
            values = dict(schedule.filters or {})
            values.update(period="custom", start_date=start, end_date=end)
            _, rows = build_report_rows(db, ReportManagementFilters(**values))
            if report_format == "xlsx":
                content = generate_report_xlsx(rows)
                extension = "xlsx"
            elif report_format == "pdf":
                content = generate_report_pdf(rows, title=report_name, period_start=start, period_end=end)
                extension = "pdf"
            elif report_format == "csv":
                content = generate_report_csv(rows)
                extension = "csv"
            else:
                raise ValueError("unsupported scheduled report format")
            REPORT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"scheduled_report_{schedule.id}_{start.date().isoformat()}_{generated.id}.{extension}"
            target = (REPORT_STORAGE_DIR / filename).resolve()
            with tempfile.NamedTemporaryFile(dir=REPORT_STORAGE_DIR, prefix=f".{filename}.", suffix=".tmp", delete=False) as temp:
                temp.write(content); temp_path = Path(temp.name)
            os.replace(temp_path, target)
            generated.status = "SUCCESS"; generated.file_path = str(target); generated.file_size = target.stat().st_size; generated.error_message = None
            schedule.last_run_at = datetime.now(_tz(schedule.timezone)).replace(tzinfo=None)
            _sync_next_run_at(schedule)
            db.commit()
            logger.info("Scheduled report %s generated at %s", schedule_id, target)
        except Exception as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            db.rollback()
            existing = db.query(GeneratedReport).filter(GeneratedReport.id == generated.id).first()
            if existing:
                existing.status = "FAILED"; existing.file_path = None; existing.file_size = None; existing.error_message = str(exc)[:500]
                db.commit()
            logger.exception("Scheduled report %s failed", schedule_id)


def sync_report_schedule(schedule: ReportSchedule) -> None:
    if not schedule.enabled:
        schedule.next_run_at = None
    if _scheduler is None:
        return
    job_id = schedule_job_id(schedule.id)
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)
    if not schedule.enabled:
        return
    hour, minute = (int(value) for value in schedule.run_time.split(":", 1))
    job = _scheduler.add_job(_run_schedule, CronTrigger(day_of_week="mon" if schedule.frequency == "weekly" else "*", day= "1" if schedule.frequency == "monthly" else "*", hour=hour, minute=minute, timezone=_tz(schedule.timezone)), args=[schedule.id], id=job_id, replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=3600)
    _sync_next_run_at(schedule)


def remove_report_schedule(schedule_id: int) -> None:
    if _scheduler is not None and _scheduler.get_job(schedule_job_id(schedule_id)):
        _scheduler.remove_job(schedule_job_id(schedule_id))


def restore_report_schedules() -> None:
    if _scheduler is None:
        return
    with SessionLocal() as db:
        for schedule in db.query(ReportSchedule).all():
            sync_report_schedule(schedule)
        db.commit()
