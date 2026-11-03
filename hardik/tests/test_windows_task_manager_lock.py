import pytest

from backend.windows_monitoring.task_manager_lock import WorkerOwnedAdvisoryLock


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class Connection:
    def __init__(self, acquire=True, release=True):
        self.acquire = acquire
        self.release = release
        self.calls = []
        self.closed = False
        self.invalidated = False

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return Result(self.acquire if len(self.calls) == 1 else self.release)

    def invalidate(self):
        self.invalidated = True

    def close(self):
        self.closed = True


def test_successful_acquisition_uses_deterministic_namespaced_key():
    connection = Connection()
    lock = WorkerOwnedAdvisoryLock(7, connection_factory=lambda: connection)
    assert lock.acquire() == "acquired"
    assert connection.calls[0][1] == {"lock_key": "nms.windows.task_manager.processes:7"}
    assert "pg_try_advisory_lock" in connection.calls[0][0]
    assert not connection.closed
    assert lock.release() == "acquired"
    assert "pg_advisory_unlock" in connection.calls[1][0]
    assert connection.closed


def test_lock_conflict_closes_connection_without_reuse():
    connection = Connection(acquire=False)
    lock = WorkerOwnedAdvisoryLock(7, connection_factory=lambda: connection)
    assert lock.acquire() == "busy"
    assert connection.closed
    assert not connection.invalidated


def test_protected_operation_success_and_lifetime():
    connection = Connection()
    events = []
    lock = WorkerOwnedAdvisoryLock(7, connection_factory=lambda: connection)
    result = lock.run(lambda: events.append((lock.state, connection.closed)) or "value")
    assert result.state == "acquired"
    assert result.value == "value"
    assert events == [("acquired", False)]
    assert connection.closed


def test_protected_operation_exception_releases_and_closes():
    connection = Connection()
    lock = WorkerOwnedAdvisoryLock(7, connection_factory=lambda: connection)
    with pytest.raises(RuntimeError):
        lock.run(lambda: (_ for _ in ()).throw(RuntimeError("protected failure")))
    assert connection.closed
    assert len(connection.calls) == 2


def test_unlock_failure_invalidates_connection_and_reports_release_error():
    connection = Connection(release=False)
    lock = WorkerOwnedAdvisoryLock(7, connection_factory=lambda: connection)
    assert lock.acquire() == "acquired"
    assert lock.release() == "release_error"
    assert connection.invalidated and connection.closed


def test_connection_creation_failure_is_explicit():
    lock = WorkerOwnedAdvisoryLock(7, connection_factory=lambda: (_ for _ in ()).throw(RuntimeError("db unavailable")))
    assert lock.acquire() == "connection_error"


def test_connection_loss_during_unlock_reports_lock_lost_and_invalidates():
    class LostConnection(Connection):
        def execute(self, statement, params):
            if len(self.calls) == 0:
                self.calls.append((str(statement), params))
                return Result(True)
            raise RuntimeError("connection lost")

    connection = LostConnection()
    lock = WorkerOwnedAdvisoryLock(7, connection_factory=lambda: connection)
    assert lock.acquire() == "acquired"
    assert lock.release() == "lock_lost"
    assert connection.invalidated and connection.closed


def test_different_devices_have_different_lock_keys():
    first = WorkerOwnedAdvisoryLock(1, connection_factory=lambda: Connection())
    second = WorkerOwnedAdvisoryLock(2, connection_factory=lambda: Connection())
    assert first.lock_key != second.lock_key


def test_request_scoped_session_is_not_accepted_or_reused():
    request_session = object()
    lock = WorkerOwnedAdvisoryLock(7, connection_factory=lambda: request_session)
    assert lock.acquire() == "connection_error"


def test_no_premature_release_while_protected_work_runs():
    connection = Connection()
    observed = []
    lock = WorkerOwnedAdvisoryLock(7, connection_factory=lambda: connection)

    def work():
        observed.append(connection.closed)
        return True

    assert lock.run(work).value is True
    assert observed == [False]
    assert connection.closed
