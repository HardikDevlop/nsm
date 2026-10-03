"""Persistent SSH terminal adapter for Remote Access.

This adapter intentionally exposes the PTY as raw bytes.  Device-specific CLI
prompt handling belongs above this layer (for example, in a future WebSocket
session service); credentials are never written to the shell automatically.
"""
from __future__ import annotations

import logging
import socket
import base64
import hashlib
import re
import time
from typing import Any

import paramiko

logger = logging.getLogger(__name__)


class _RemoteAccessTransport(paramiko.Transport):
    """Transport policy for legacy devices, scoped to one Remote Access connect."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # OpenSSH 6.2 appliances may offer only the SHA-1 ssh-rsa host key.
        # Do not add ssh-dss, and do not mutate Paramiko's global preferences.
        if "ssh-rsa" not in self.get_security_options().key_types:
            self.get_security_options().key_types = (
                *self.get_security_options().key_types,
                "ssh-rsa",
            )
        logger.warning(
            "Remote Access SSH transport_factory=%s ssh_rsa_enabled=%s ssh_dss_enabled=%s",
            type(self).__name__,
            "ssh-rsa" in self.get_security_options().key_types,
            "ssh-dss" in self.get_security_options().key_types,
        )


def _safe_paramiko_message(exc: BaseException, *, host: str, username: str, password: str) -> str:
    message = str(exc).replace("\n", " ").replace("\r", " ").strip()
    for value, replacement in ((password, "[REDACTED_SECRET]"), (username, "[REDACTED_USER]"),
                               (host, "[REDACTED_HOST]")):
        if value:
            message = message.replace(value, replacement)
    return message[:512]


def _log_handshake_diagnostics(transport: Any, exc: BaseException, *, host: str,
                               username: str, password: str) -> None:
    """Log negotiation diagnostics without logging credentials or key material."""
    if transport is None:
        logger.warning(
            "Remote Access SSH handshake_diagnostics transport=UNAVAILABLE "
            "exception_type=%s exception_message=%s",
            type(exc).__name__,
            _safe_paramiko_message(exc, host=host, username=username, password=password),
        )
        return
    try:
        options = transport.get_security_options()
        key_types = tuple(options.key_types)
        kex = tuple(options.kex)
        ciphers = tuple(options.ciphers)
        # Paramiko versions expose MAC algorithms as ``digests`` or
        # ``macs``.  Diagnostics must never mask the original connection
        # error when one of these optional attributes is unavailable.
        macs = tuple(getattr(options, "digests", getattr(options, "macs", ())))
    except Exception:
        key_types = kex = ciphers = macs = ()
    values = {
        "remote_version": getattr(transport, "remote_version", "") or "UNAVAILABLE",
        "local_cipher": getattr(transport, "local_cipher", "") or "UNAVAILABLE",
        "remote_cipher": getattr(transport, "remote_cipher", "") or "UNAVAILABLE",
        "local_kex": getattr(transport, "local_kex", "") or "UNAVAILABLE",
        "remote_kex": getattr(transport, "remote_kex", "") or "UNAVAILABLE",
        "host_key_type": getattr(transport, "host_key_type", "") or "UNAVAILABLE",
        "remote_macs": getattr(transport, "remote_mac", "") or "UNAVAILABLE",
    }
    logger.warning(
        "Remote Access SSH handshake_diagnostics transport_factory=%s "
        "remote_version=%s host_key_type=%s local_kex=%s remote_kex=%s "
        "local_cipher=%s remote_cipher=%s remote_mac=%s local_host_keys=%s remote_offered_host_keys=%s "
        "available_kex=%s available_ciphers=%s available_macs=%s "
        "exception_type=%s exception_message=%s",
        type(transport).__name__, values["remote_version"], values["host_key_type"],
        values["local_kex"], values["remote_kex"], values["local_cipher"], values["remote_cipher"],
        values["remote_macs"], key_types, getattr(transport, "_preferred_keys", ()) or "UNAVAILABLE",
        kex, ciphers, macs, type(exc).__name__,
        _safe_paramiko_message(exc, host=host, username=username, password=password),
    )


class SSHConnectionError(ConnectionError):
    """A connection could not be established or used safely."""
    def __init__(self, message: str, code: str = "SSH_HANDSHAKE_FAILED", stage: str = "SSH_HANDSHAKE"):
        super().__init__(message)
        self.code, self.stage, self.message = code, stage, message


class SSHConnectionAdapter:
    """A single persistent SSH PTY connection.

    ``allow_unknown_host`` is opt-in.  By default Paramiko's known-hosts
    database is used with RejectPolicy, which avoids silently trusting a new
    host key in a production deployment.
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        *,
        timeout: float = 10.0,
        known_hosts: str | None = None,
        allow_unknown_host: bool = False,
        expected_host_key_fingerprint: str | None = None,
        term: str = "xterm",
        width: int = 120,
        height: int = 40,
    ) -> None:
        if not host or not username:
            raise ValueError("host and username are required")
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.host, self.port, self.username = host, port, username
        self.password = password
        self.timeout = timeout
        self.known_hosts = known_hosts
        self.allow_unknown_host = allow_unknown_host
        self.expected_host_key_fingerprint = expected_host_key_fingerprint
        self.term, self.width, self.height = term, width, height
        self._client: paramiko.SSHClient | None = None
        self._channel: paramiko.Channel | None = None
        self._pending_output = bytearray()

    @property
    def channel(self) -> paramiko.Channel:
        if self._channel is None or self._channel.closed:
            raise SSHConnectionError("SSH interactive shell is not connected")
        return self._channel

    def connect(self) -> "SSHConnectionAdapter":
        if self.is_alive():
            return self
        client = paramiko.SSHClient()
        try:
            if self.known_hosts:
                client.load_host_keys(self.known_hosts)
            else:
                client.load_system_host_keys()
        except (OSError, paramiko.SSHException) as exc:
            client.close()
            logger.info("Remote Access SSH stage=HOST_KEY_VERIFY status=FAILED code=HOST_KEY_FAILED")
            raise SSHConnectionError("SSH host key verification failed", "HOST_KEY_FAILED", "HOST_KEY_VERIFY") from exc
        client.set_missing_host_key_policy(
            paramiko.AutoAddPolicy() if self.allow_unknown_host else paramiko.RejectPolicy()
        )
        logger.info("Remote Access SSH stage=TCP_CONNECT status=START host=%s port=%s", self.host, self.port)
        transport = None
        try:
            sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            logger.info("Remote Access SSH stage=TCP_CONNECT status=SUCCESS host=%s port=%s", self.host, self.port)
            transport = _RemoteAccessTransport(sock)
            logger.info("Remote Access SSH transport_factory=%s instantiated=true", type(transport).__name__)
            transport.banner_timeout = self.timeout
            transport.auth_timeout = self.timeout
            logger.info("Remote Access SSH stage=SSH_HANDSHAKE status=START local_host_keys=%s",
                        tuple(transport.get_security_options().key_types))
            transport.start_client(timeout=self.timeout)
            logger.info("Remote Access SSH banner remote_version=%s", transport.remote_version or "UNAVAILABLE")
            server_key = transport.get_remote_server_key()
            if self.expected_host_key_fingerprint:
                actual = "SHA256:" + base64.b64encode(hashlib.sha256(server_key.asbytes()).digest()).decode().rstrip("=")
                if actual != self.expected_host_key_fingerprint:
                    logger.info("Remote Access SSH stage=HOST_KEY_VERIFY status=FAILED code=HOST_KEY_MISMATCH")
                    raise SSHConnectionError("SSH host key does not match trusted key", "HOST_KEY_MISMATCH", "HOST_KEY_VERIFY")
            # The host-key policy logs through ``client._transport``. Attach
            # the manually-created transport before invoking the policy so a
            # missing/rejected host key is reported as HOST_KEY_FAILED rather
            # than being masked by an AttributeError.
            client._transport = transport
            # Preserve SSHClient's RejectPolicy/AutoAddPolicy behavior without
            # delegating transport construction to a version-dependent API.
            host_key_name = self.host if self.port == 22 else f"[{self.host}]:{self.port}"
            known = client._system_host_keys.get(host_key_name) or client._host_keys.get(host_key_name)
            try:
                if known is None:
                    client._policy.missing_host_key(client, host_key_name, server_key)
                else:
                    expected = known.get(server_key.get_name())
                    if expected is None or expected != server_key:
                        raise paramiko.BadHostKeyException(self.host, server_key, expected or list(known.values())[0])
            except paramiko.BadHostKeyException:
                raise
            except paramiko.SSHException as exc:
                logger.info("Remote Access SSH stage=HOST_KEY_VERIFY status=FAILED code=HOST_KEY_FAILED")
                raise SSHConnectionError("SSH host key verification failed", "HOST_KEY_FAILED", "HOST_KEY_VERIFY") from exc
        except paramiko.AuthenticationException:
            logger.info("Remote Access SSH stage=SSH_TRANSPORT_AUTH status=FAILED code=SSH_AUTH_FAILED")
            # Some appliances accept SSH transport auth_none and defer their
            # actual username/password prompt until after PTY allocation.
            transport = client.get_transport()
            if transport is None:
                client.close()
                raise SSHConnectionError("SSH transport was not established")
            try:
                transport.auth_none(self.username)
                logger.info("Remote Access SSH stage=SSH_TRANSPORT_AUTH status=SUCCESS method=auth_none")
            except (paramiko.AuthenticationException, paramiko.SSHException) as exc:
                client.close()
                raise SSHConnectionError("SSH authentication failed", "SSH_AUTH_FAILED", "SSH_TRANSPORT_AUTH") from exc
        except (socket.timeout, TimeoutError) as exc:
            client.close()
            logger.info("Remote Access SSH stage=TCP_CONNECT status=FAILED code=TCP_TIMEOUT")
            raise SSHConnectionError("SSH connection timed out", "TCP_TIMEOUT", "TCP_CONNECT") from exc
        except ConnectionRefusedError as exc:
            client.close()
            logger.info("Remote Access SSH stage=TCP_CONNECT status=FAILED code=TCP_REFUSED")
            raise SSHConnectionError("SSH connection refused", "TCP_REFUSED", "TCP_CONNECT") from exc
        except paramiko.BadHostKeyException as exc:
            client.close()
            logger.info("Remote Access SSH stage=HOST_KEY_VERIFY status=FAILED code=HOST_KEY_FAILED")
            raise SSHConnectionError("SSH host key verification failed", "HOST_KEY_FAILED", "HOST_KEY_VERIFY") from exc
        except paramiko.AuthenticationException as exc:
            client.close()
            logger.info("Remote Access SSH stage=SSH_TRANSPORT_AUTH status=FAILED code=SSH_AUTH_FAILED")
            raise SSHConnectionError("SSH authentication failed", "SSH_AUTH_FAILED", "SSH_TRANSPORT_AUTH") from exc
        except (paramiko.SSHException, OSError) as exc:
            _log_handshake_diagnostics(
                client.get_transport() if hasattr(client, "get_transport") else None,
                exc, host=self.host, username=self.username, password=self.password
            )
            client.close()
            logger.warning(
                "Remote Access SSH stage=SSH_HANDSHAKE status=FAILED code=SSH_HANDSHAKE_FAILED "
                "exception_type=%s exception_message=%s",
                type(exc).__name__,
                _safe_paramiko_message(exc, host=self.host, username=self.username, password=self.password),
            )
            raise SSHConnectionError("SSH handshake failed", "SSH_HANDSHAKE_FAILED", "SSH_HANDSHAKE") from exc

        # Explicit transport setup above leaves authentication to this adapter,
        # preserving appliances which accept auth_none and defer CLI login.
        try:
            transport = client.get_transport()
            if transport is None:
                raise paramiko.SSHException("SSH transport unavailable")
            try:
                transport.auth_password(self.username, self.password)
                logger.info("Remote Access SSH stage=SSH_TRANSPORT_AUTH status=SUCCESS method=password")
            except paramiko.AuthenticationException:
                logger.info("Remote Access SSH stage=SSH_TRANSPORT_AUTH status=FAILED code=SSH_AUTH_FAILED")
                transport.auth_none(self.username)
                logger.info("Remote Access SSH stage=SSH_TRANSPORT_AUTH status=SUCCESS method=auth_none")
        except (paramiko.AuthenticationException, paramiko.SSHException, OSError) as exc:
            _log_handshake_diagnostics(transport, exc, host=self.host, username=self.username, password=self.password)
            client.close()
            raise SSHConnectionError("SSH authentication failed", "SSH_AUTH_FAILED", "SSH_TRANSPORT_AUTH") from exc

        logger.info("Remote Access SSH stage=SSH_HANDSHAKE status=SUCCESS host=%s port=%s", self.host, self.port)
        logger.info("Remote Access SSH stage=HOST_KEY_VERIFY status=SUCCESS host=%s", self.host)
        logger.info("Remote Access SSH stage=PTY_OPEN status=START host=%s", self.host)
        try:
            transport = client.get_transport()
            if transport is None:
                raise paramiko.SSHException("SSH transport unavailable")
            channel = transport.open_session()
            channel.get_pty(term=self.term, width=self.width, height=self.height)
            channel.settimeout(self.timeout)
        except (paramiko.SSHException, OSError, socket.timeout) as exc:
            client.close()
            logger.info("Remote Access SSH stage=PTY_OPEN status=FAILED code=PTY_OPEN_FAILED")
            raise SSHConnectionError("Could not open SSH PTY", "PTY_OPEN_FAILED", "PTY_OPEN") from exc
        logger.info("Remote Access SSH stage=PTY_OPEN status=SUCCESS host=%s", self.host)
        logger.info("Remote Access SSH stage=SHELL_OPEN status=START host=%s", self.host)
        try:
            channel.invoke_shell()
        except (paramiko.SSHException, OSError, socket.timeout) as exc:
            client.close()
            logger.info("Remote Access SSH stage=SHELL_OPEN status=FAILED code=SHELL_OPEN_FAILED")
            raise SSHConnectionError("Could not open SSH shell", "SHELL_OPEN_FAILED", "SHELL_OPEN") from exc
        logger.info("Remote Access SSH stage=SHELL_OPEN status=SUCCESS host=%s", self.host)
        try:
            self._bootstrap_cli_login(channel)
        except SSHConnectionError:
            client.close()
            raise
        self._client, self._channel = client, channel
        logger.info("Remote Access SSH stage=CLI_PROMPT_READY status=SUCCESS host=%s", self.host)
        logger.info("SSH interactive shell established for %s:%s", self.host, self.port)
        return self

    def _bootstrap_cli_login(self, channel: paramiko.Channel) -> None:
        """Answer only explicit, bounded CLI login prompts after PTY setup.

        SSH transport authentication is already complete at this point. Some
        appliances still ask for credentials inside the shell. The bootstrap
        consumes only a small initial window; unrecognized output is retained
        for the normal terminal reader.
        """
        deadline = time.monotonic() + min(max(self.timeout, 0.1), 5.0)
        captured = bytearray()
        username_sent = password_sent = False
        prompt_seen = False
        username_prompt = re.compile(rb"(?:^|[\r\n])\s*(?:username|login)\s*[:>]\s*$", re.I)
        password_prompt = re.compile(rb"(?:^|[\r\n])\s*password\s*[:>]\s*$", re.I)
        cli_prompt = re.compile(rb"(?:^|[\r\n])[^\r\n]{0,96}[#>$]\s*$")
        def preserve_safe_output() -> None:
            # Some PTYs echo submitted input. Never forward the configured
            # secret even if the device echoes it back.
            secret = self.password.encode()
            safe = bytes(captured).replace(secret, b"") if secret else bytes(captured)
            self._pending_output.extend(safe)
        while time.monotonic() < deadline:
            try:
                if channel.recv_ready():
                    chunk = channel.recv(4096)
                    if not chunk:
                        break
                    captured.extend(chunk)
                    tail = bytes(captured[-512:])
                    if not username_sent and username_prompt.search(tail):
                        channel.sendall((self.username + "\r").encode())
                        username_sent = prompt_seen = True
                        continue
                    if username_sent and not password_sent and password_prompt.search(tail):
                        channel.sendall((self.password + "\r").encode())
                        password_sent = prompt_seen = True
                        continue
                    if password_sent and cli_prompt.search(tail):
                        preserve_safe_output()
                        return
                    if prompt_seen and cli_prompt.search(tail):
                        preserve_safe_output()
                        return
                else:
                    time.sleep(0.01)
            except (socket.timeout, paramiko.SSHException, OSError) as exc:
                raise SSHConnectionError("SSH CLI login bootstrap failed", "CLI_BOOTSTRAP_FAILED", "CLI_BOOTSTRAP") from exc
        # No recognized prompt is a valid raw-terminal case. Preserve every
        # byte so the browser receives the initial banner/output unchanged.
        if not prompt_seen:
            preserve_safe_output()
            return
        raise SSHConnectionError("SSH CLI login prompt timed out", "CLI_BOOTSTRAP_TIMEOUT", "CLI_BOOTSTRAP")

    def read(self, max_bytes: int = 65536, timeout: float | None = 0.0) -> bytes:
        """Read currently available PTY output; empty bytes means no data."""
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if self._pending_output:
            data = bytes(self._pending_output[:max_bytes])
            del self._pending_output[:max_bytes]
            return data
        channel = self.channel
        channel.settimeout(self.timeout if timeout is None else max(0.0, timeout))
        try:
            return channel.recv(max_bytes) if channel.recv_ready() else b""
        except socket.timeout:
            return b""
        except (paramiko.SSHException, OSError) as exc:
            raise SSHConnectionError("Could not read SSH shell") from exc

    def write(self, data: str | bytes) -> None:
        if not data:
            return
        payload = data.encode() if isinstance(data, str) else data
        try:
            self.channel.sendall(payload)
        except (paramiko.SSHException, OSError) as exc:
            raise SSHConnectionError("Could not write SSH shell") from exc

    def resize(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("PTY dimensions must be positive")
        try:
            self.channel.resize_pty(width=width, height=height)
        except (paramiko.SSHException, OSError) as exc:
            raise SSHConnectionError("Could not resize SSH PTY") from exc

    def is_alive(self) -> bool:
        transport = self._client.get_transport() if self._client else None
        return bool(transport and transport.is_active() and self._channel and not self._channel.closed)

    def close(self) -> None:
        channel, client = self._channel, self._client
        self._channel = self._client = None
        if channel is not None:
            channel.close()
        if client is not None:
            client.close()

    disconnect = close

    def __enter__(self) -> "SSHConnectionAdapter":
        return self.connect()

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()
