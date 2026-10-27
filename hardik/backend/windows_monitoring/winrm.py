"""Small, HTTPS-only WinRM connectivity adapter."""

from dataclasses import dataclass
import base64
import ipaddress
import json
import logging
import re
from typing import Any, Callable
from urllib.parse import urlparse

import winrm
from pypsrp.powershell import PowerShell, RunspacePool
from pypsrp.wsman import WSMan
from requests.exceptions import SSLError
from winrm.exceptions import (
    AuthenticationError,
    InvalidCredentialsError,
    WinRMOperationTimeoutError,
    WinRMTransportError,
    WSManFaultError,
)


_HOSTNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,253}[A-Za-z0-9])?$")
_TEST_COMMAND = "$PSVersionTable.PSVersion.ToString()"
_POWERSHELL = "powershell.exe"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WinRMConnectionDiagnostic:
    """Safe connection result; it deliberately contains no remote output."""

    ok: bool
    category: str
    message: str


class WinRMHTTPSAdapter:
    """Connect to an existing Windows host using WinRM HTTPS and NTLM."""

    def __init__(
        self,
        hostname: str,
        username: str,
        password: str,
        *,
        port: int = 5986,
        ca_trust_path: str | None = None,
        connect_timeout: int = 30,
        operation_timeout: int = 20,
        session_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._validate_target(hostname, port)
        if not username or not password:
            raise ValueError("username and password are required")
        if connect_timeout <= 0 or operation_timeout <= 0:
            raise ValueError("timeouts must be positive")

        self.hostname = hostname
        self.port = port
        self.username = username
        self._password = password
        self.ca_trust_path = ca_trust_path
        self.connect_timeout = connect_timeout
        self.operation_timeout = operation_timeout
        self._session_factory = session_factory or winrm.Session

    @staticmethod
    def _validate_target(hostname: str, port: int) -> None:
        if not isinstance(hostname, str) or not hostname or hostname != hostname.strip():
            raise ValueError("hostname must be a bare host or IP address")
        if urlparse(hostname).scheme or "/" in hostname or "://" in hostname:
            raise ValueError("hostname must not contain a URL or path")
        try:
            valid_ip = ipaddress.ip_address(hostname)
        except ValueError:
            valid_ip = None
        if valid_ip is None and not _HOSTNAME.fullmatch(hostname):
            raise ValueError("malformed hostname")
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")

    def _session(self) -> Any:
        endpoint = f"https://{self.hostname}:{self.port}/wsman"
        # pywinrm requires the HTTP read timeout to be strictly greater than
        # the WSMan operation timeout. The CIM client may legitimately provide
        # equal or smaller connection/read values, so normalize only this
        # pywinrm-specific constructor requirement.
        read_timeout = max(self.connect_timeout, self.operation_timeout + 1)
        return self._session_factory(
            endpoint,
            auth=(self.username, self._password),
            transport="ntlm",
            server_cert_validation="validate",
            # Match the verified pypsrp collector: use the configured CA when
            # supplied, otherwise let Requests use the system trust store.
            # Certificate validation remains enabled in all cases.
            ca_trust_path=self.ca_trust_path or None,
            read_timeout_sec=read_timeout,
            operation_timeout_sec=self.operation_timeout,
        )

    @staticmethod
    def _classify(error: Exception) -> WinRMConnectionDiagnostic:
        if isinstance(error, (AuthenticationError, InvalidCredentialsError)):
            return WinRMConnectionDiagnostic(False, "authentication", "WinRM authentication failed")
        if isinstance(error, WinRMOperationTimeoutError):
            return WinRMConnectionDiagnostic(False, "timeout", "WinRM operation timed out")
        if isinstance(error, SSLError):
            return WinRMConnectionDiagnostic(False, "tls", "TLS certificate validation failed")
        if isinstance(error, WSManFaultError):
            return WinRMConnectionDiagnostic(False, "protocol", "WinRM protocol error")
        if isinstance(error, WinRMTransportError):
            return WinRMConnectionDiagnostic(False, "network", "WinRM network connection failed")
        return WinRMConnectionDiagnostic(False, "protocol", "WinRM protocol error")

    def _log_system_event_failure(self, stage: str, error: Exception) -> None:
        """Log only safe metadata for the System event collector path."""
        def safe_attr(name: str):
            try:
                return getattr(error, name, None)
            except Exception:
                return None

        fault_code = safe_attr("fault_code") or safe_attr("wsman_fault_code")
        numeric_code = safe_attr("code")
        reason = safe_attr("reason")
        if isinstance(reason, str):
            reason = re.sub(r"[\r\n\t]+", " ", reason)[:240]
        logger.warning(
            "windows_system_event_failure stage=%s host=%s exception_type=%s category=%s "
            "fault_code=%s numeric_code=%s reason=%s",
            stage,
            self.hostname,
            type(error).__name__,
            self._classify(error).category,
            fault_code,
            numeric_code,
            reason or "unknown",
        )

    def _run_event_powershell(self, command: str) -> tuple[bytes, bytes, int]:
        """Run the event query through the working pypsrp WSMan transport.

        pywinrm reaches the endpoint but fails during WinRS shell creation on
        this host. pypsrp uses the WSMan runspace path already used by the
        successful CIM collector, without changing authentication or TLS.
        """
        stage = "pypsrp_session_creation"
        wsman = None
        pool = None
        try:
            wsman = WSMan(
                self.hostname,
                port=self.port,
                username=self.username,
                password=self._password,
                ssl=True,
                auth="ntlm",
                # pypsrp forwards a string cert_validation value to
                # requests.Session.verify, so this preserves the configured
                # CA bundle. With no configured bundle, True uses the system
                # trust store. False is never allowed here.
                cert_validation=self.ca_trust_path or True,
                connection_timeout=self.connect_timeout,
                read_timeout=max(self.connect_timeout, self.operation_timeout + 1),
                operation_timeout=self.operation_timeout,
                path="wsman",
            )
            stage = "pypsrp_runspace_creation"
            pool = RunspacePool(wsman, no_profile=True)
            pool.open()
            stage = "pypsrp_command_execution"
            powershell = PowerShell(pool)
            powershell.add_script(command)
            output = powershell.invoke()
            errors = getattr(getattr(powershell, "streams", None), "error", None) or []
            stdout = "\n".join(str(item) for item in output).encode("utf-8")
            stderr = "\n".join(str(item) for item in errors).encode("utf-8")
            return stdout, stderr, 1 if errors else 0
        except Exception as error:
            self._log_system_event_failure(stage, error)
            raise
        finally:
            if pool is not None:
                try:
                    pool.close()
                except Exception as error:
                    self._log_system_event_failure("pypsrp_runspace_cleanup", error)
            if wsman is not None:
                try:
                    wsman.close()
                except Exception as error:
                    self._log_system_event_failure("pypsrp_session_cleanup", error)

    @staticmethod
    def _encoded_powershell(command: str) -> str:
        """Return PowerShell's UTF-16LE Base64 encoded command form."""
        return base64.b64encode(command.encode("utf-16le")).decode("ascii")

    def _run_powershell(self, session: Any, command: str) -> tuple[bytes, bytes, int]:
        """Execute one encoded command through an explicitly managed shell.

        pywinrm's convenience ``run_ps`` path does not expose the shell
        options needed by standalone/workgroup non-admin hosts. Keep all
        protocol objects local and always clean up both command and shell.
        """
        protocol = session.protocol
        shell_id = None
        command_id = None
        stage = "shell_creation"
        try:
            # Keep the remote shell profile disabled for predictable command
            # execution on standalone/workgroup hosts. pywinrm exposes this
            # option on its low-level Protocol API.
            shell_id = protocol.open_shell(noprofile=True)
            encoded = self._encoded_powershell(command)
            stage = "command_execution"
            command_id = protocol.run_command(
                shell_id,
                _POWERSHELL,
                ["-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            )
            stage = "command_output"
            stdout, stderr, status_code = protocol.get_command_output(shell_id, command_id)
            return stdout, stderr, status_code
        except Exception as error:
            self._log_system_event_failure(stage, error)
            raise
        finally:
            try:
                if shell_id is not None and command_id is not None:
                    stage = "command_cleanup"
                    try:
                        protocol.cleanup_command(shell_id, command_id)
                    except Exception as error:
                        # Cleanup failures must not discard a valid command
                        # response (some WinRM providers close commands
                        # implicitly after returning output).
                        self._log_system_event_failure(stage, error)
            finally:
                if shell_id is not None:
                    try:
                        stage = "shell_cleanup"
                        protocol.close_shell(shell_id)
                    except Exception as error:
                        # The shell is already remote state; a close failure
                        # after successful output is non-fatal to collection.
                        self._log_system_event_failure(stage, error)

    def test_connection(self) -> WinRMConnectionDiagnostic:
        """Run only a harmless PowerShell version read on the remote host."""
        stage = "session_creation"
        try:
            session = self._session()
            _stdout, _stderr, status_code = self._run_powershell(session, _TEST_COMMAND)
            if status_code != 0:
                return WinRMConnectionDiagnostic(False, "protocol", "WinRM command failed")
            return WinRMConnectionDiagnostic(True, "success", "WinRM HTTPS connection succeeded")
        except Exception as error:  # library exposes several transport wrappers
            logger.warning(
                "windows_winrm_failure stage=%s host=%s exception_type=%s category=%s",
                stage, self.hostname, type(error).__name__, self._classify(error).category,
            )
            return self._classify(error)

    def query_system_events(
        self,
        *,
        start_time: str,
        end_time: str,
        event_ids: tuple[int, ...],
        max_records: int,
    ) -> tuple[bytes, bytes, int]:
        """Run the fixed, read-only System event query over this WinRM session."""
        if not 1 <= max_records <= 50:
            raise ValueError("max_records must be between 1 and 50")
        if any(not isinstance(event_id, int) or isinstance(event_id, bool) or event_id < 0 for event_id in event_ids):
            raise ValueError("event_ids must contain non-negative integers")

        # Values are JSON-encoded before being embedded as PowerShell literals;
        # the channel and cmdlet are constants and never caller-controlled.
        ps_start = json.dumps(start_time)
        ps_end = json.dumps(end_time)
        ps_ids = "@(" + ",".join(str(event_id) for event_id in event_ids) + ")" if event_ids else "$null"
        script = f"""
$ErrorActionPreference = 'Stop'
$filter = @{{ LogName = 'System'; StartTime = [DateTime]::Parse({ps_start}); EndTime = [DateTime]::Parse({ps_end}) }}
if ($null -ne {ps_ids}) {{ $filter.Id = {ps_ids} }}
$items = @()
try {{
  $items = @(Get-WinEvent -FilterHashtable $filter -MaxEvents {max_records + 1} -ErrorAction Stop | Select-Object -First {max_records + 1})
}} catch {{
  # Get-WinEvent reports an empty result as a terminating error. Treat only
  # that documented condition as an empty collection; preserve permission,
  # channel, and provider failures for the caller.
  if ($_.Exception.Message -notmatch 'No events were found|No events found') {{ throw }}
}}
$records = @($items | Select-Object -First {max_records} | ForEach-Object {{
  [ordered]@{{
    record_id = [long]$_.RecordId
    time_created = if ($_.TimeCreated) {{ $_.TimeCreated.ToUniversalTime().ToString('o') }} else {{ $null }}
    event_id = [int]$_.Id
    provider = $_.ProviderName
    level = $_.LevelDisplayName
    machine_name = $_.MachineName
    message = $_.Message
    user_id = if ($_.UserId) {{ $_.UserId.Value }} else {{ $null }}
  }}
}})
[ordered]@{{ events = $records; truncated = ($items.Count -gt {max_records}) }} | ConvertTo-Json -Compress -Depth 5
"""
        try:
            return self._run_event_powershell(script)
        except Exception as error:
            self._log_system_event_failure("event_query", error)
            raise
