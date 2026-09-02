"""Durable, isolated scheduler for Linux Server Monitoring only."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from backend.database.session import SessionLocal
from backend.linux_monitoring import service
from backend.linux_monitoring.models import LinuxServerMonitoringConfig, LinuxServerSNMPCredential, linux_now

LINUX_POLL_INTERVAL_SECONDS = 180


class LinuxMonitoringScheduler:
    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="linux-monitor")
        self._retention_task: asyncio.Task[None] | None = None
        self._last_cleanup_at = None
        self._last_cleanup_error = None

    async def restore_enabled_servers(self) -> None:
        if self._retention_task is None or self._retention_task.done():
            self._retention_task = asyncio.create_task(self._run_retention(), name="linux-monitor-retention")
        with SessionLocal() as db:
            server_ids = [row[0] for row in db.query(LinuxServerMonitoringConfig.linux_server_id).filter(
                LinuxServerMonitoringConfig.enabled.is_(True)
            ).all()]
        for server_id in server_ids:
            try:
                await self.start_server(server_id, persist=False)
            except Exception as exc:
                self._record_failure(server_id, str(exc))

    async def start_server(self, server_id: int, persist: bool = True) -> dict:
        async with self._lock:
            with SessionLocal() as db:
                server = service.get_server(db, server_id)
                config = db.query(LinuxServerMonitoringConfig).filter_by(linux_server_id=server.id).first()
                if config is None:
                    config = LinuxServerMonitoringConfig(linux_server_id=server.id)
                    db.add(config)
                    db.flush()
                if persist:
                    config.enabled = True
                config.interval_seconds = LINUX_POLL_INTERVAL_SECONDS
                credential = db.query(LinuxServerSNMPCredential).filter_by(
                    linux_server_id=server.id, enabled=True
                ).first()
                if credential is None:
                    config.monitoring_status = "failed"
                    config.last_error = "SNMPv3 credentials are not configured"
                    db.commit()
                    return self._status(config)
                config.monitoring_status = "running"
                config.last_started_at = linux_now()
                config.last_error = None
                db.commit()
                status = self._status(config)
            task = self._tasks.get(server_id)
            if task is None or task.done():
                self._tasks[server_id] = asyncio.create_task(self._run(server_id), name=f"linux-monitor-{server_id}")
            return status

    async def stop_server(self, server_id: int) -> dict:
        async with self._lock:
            with SessionLocal() as db:
                server = service.get_server(db, server_id)
                config = db.query(LinuxServerMonitoringConfig).filter_by(linux_server_id=server.id).first()
                if config is None:
                    config = LinuxServerMonitoringConfig(linux_server_id=server.id)
                    db.add(config)
                config.enabled = False
                config.monitoring_status = "stopped"
                config.interval_seconds = LINUX_POLL_INTERVAL_SECONDS
                config.last_stopped_at = linux_now()
                db.commit()
                status = self._status(config)
            task = self._tasks.pop(server_id, None)
            if task and not task.done():
                task.cancel()
            return status

    def status(self, server_id: int) -> dict:
        with SessionLocal() as db:
            service.get_server(db, server_id)
            config = db.query(LinuxServerMonitoringConfig).filter_by(linux_server_id=server_id).first()
            if config is None:
                return {"server_id": server_id, "enabled": False, "status": "stopped", "interval_seconds": LINUX_POLL_INTERVAL_SECONDS}
            return self._status(config)

    def statuses(self) -> list[dict]:
        with SessionLocal() as db:
            rows = db.query(LinuxServerMonitoringConfig).all()
            return [self._status(row) for row in rows]

    def retention_status(self) -> dict:
        return {
            "retention_hours": 24,
            "last_cleanup_at": self._last_cleanup_at,
            "last_cleanup_error": self._last_cleanup_error,
        }

    async def _run(self, server_id: int) -> None:
        try:
            while True:
                try:
                    payload = None
                    missing_credentials = False
                    with SessionLocal() as db:
                        config = db.query(LinuxServerMonitoringConfig).filter_by(linux_server_id=server_id).first()
                        if config is None or not config.enabled:
                            return
                        credential = db.query(LinuxServerSNMPCredential).filter_by(
                            linux_server_id=server_id, enabled=True
                        ).first()
                        if credential is None:
                            missing_credentials = True
                        else:
                            payload = service.metrics_payload_from_credential(credential)
                    if missing_credentials:
                        self._record_failure(server_id, "SNMPv3 credentials are not configured")
                    elif payload is not None:
                        loop = asyncio.get_running_loop()
                        collected = False
                        for attempt in range(2):
                            collected = await loop.run_in_executor(
                                self._executor, self._collect_once, server_id, payload
                            )
                            if collected or attempt == 1:
                                break
                            # Retry one transient SNMP response before exposing
                            # the cycle as failed to the operator.
                            await asyncio.sleep(2)
                except Exception as exc:
                    # A single bad response or collector error must not kill an
                    # enabled server's monitoring task. The next cycle can recover.
                    self._record_failure(server_id, str(exc))
                await asyncio.sleep(LINUX_POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise

    @staticmethod
    def _collect_once(server_id: int, payload) -> bool:
        with SessionLocal() as db:
            attempt_started_at = linux_now()
            sample, error = service.collect_metrics(db, server_id, payload)
            config = db.query(LinuxServerMonitoringConfig).filter_by(linux_server_id=server_id).first()
            if config is None:
                return False
            config.last_run_at = linux_now()
            if error:
                # Another worker may have completed a newer successful poll
                # while this attempt was in flight. Do not let that stale
                # failure overwrite a healthy status.
                if not config.last_success_at or config.last_success_at < attempt_started_at:
                    config.monitoring_status = "failed"
                    config.last_error = error.message
                else:
                    config.monitoring_status = "running"
                    config.last_error = None
            else:
                config.monitoring_status = "running"
                config.last_success_at = sample.collected_at if sample else linux_now()
                config.last_error = None
            db.commit()
            return error is None

    @staticmethod
    def _record_failure(server_id: int, message: str) -> None:
        with SessionLocal() as db:
            config = db.query(LinuxServerMonitoringConfig).filter_by(linux_server_id=server_id).first()
            if config:
                config.monitoring_status = "failed"
                config.last_run_at = linux_now()
                config.last_error = message[:2000]
                db.commit()

    @staticmethod
    def _status(config: LinuxServerMonitoringConfig) -> dict:
        return {
            "server_id": config.linux_server_id,
            "enabled": config.enabled,
            "status": config.monitoring_status,
            "interval_seconds": LINUX_POLL_INTERVAL_SECONDS,
            "last_run_at": config.last_run_at,
            "last_success_at": config.last_success_at,
            "last_started_at": config.last_started_at,
            "last_stopped_at": config.last_stopped_at,
            "last_error": config.last_error,
        }

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._retention_task and not self._retention_task.done():
            self._retention_task.cancel()
            await asyncio.gather(self._retention_task, return_exceptions=True)
        self._executor.shutdown(wait=False, cancel_futures=True)

    async def _run_retention(self) -> None:
        try:
            while True:
                loop = asyncio.get_running_loop()
                try:
                    await loop.run_in_executor(self._executor, self._cleanup_once)
                    self._last_cleanup_at = linux_now()
                    self._last_cleanup_error = None
                except Exception as exc:
                    self._last_cleanup_error = str(exc)[:2000]
                await asyncio.sleep(900)
        except asyncio.CancelledError:
            raise

    def _cleanup_once(self) -> None:
        with SessionLocal() as db:
            service.cleanup_expired_history(db, linux_now() - timedelta(hours=24))
