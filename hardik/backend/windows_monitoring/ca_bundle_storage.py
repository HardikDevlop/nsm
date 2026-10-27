"""Fail-closed private filesystem storage for Windows CA bundle bytes.

This module provides storage safety only. It does not parse certificates,
validate CA semantics, or mark uploaded bytes as trusted.
"""

from __future__ import annotations

import os
import re
import secrets
import stat
from pathlib import Path

from backend.config.settings import get_settings


class CABundleStorageError(RuntimeError):
    """Base class for safe, API-independent CA storage failures."""


class InvalidStorageConfiguration(CABundleStorageError):
    pass


class InvalidStorageKey(CABundleStorageError):
    pass


class UnsafeStoragePath(CABundleStorageError):
    pass


class StorageWriteError(CABundleStorageError):
    pass


class BundleNotFound(CABundleStorageError):
    pass


class StorageDeleteError(CABundleStorageError):
    pass


_STORAGE_KEY = re.compile(r"^ca-[0-9a-f]{32}\.pem$")
_TEMP_PREFIX = ".ca-"


def _configured_root() -> Path:
    configured = get_settings().windows_ca_storage_root.strip()
    if not configured:
        raise InvalidStorageConfiguration("Windows CA storage is not configured")
    root = Path(configured)
    if not root.is_absolute():
        raise InvalidStorageConfiguration("Windows CA storage configuration is invalid")
    try:
        info = root.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise InvalidStorageConfiguration("Windows CA storage configuration is unsafe")
        if stat.S_IMODE(info.st_mode) != 0o700:
            raise InvalidStorageConfiguration("Windows CA storage permissions are unsafe")
        if not os.access(root, os.R_OK | os.W_OK | os.X_OK):
            raise InvalidStorageConfiguration("Windows CA storage is not accessible")
    except OSError:
        raise InvalidStorageConfiguration("Windows CA storage configuration is unavailable") from None
    return root


def _validate_key(storage_key: str) -> str:
    if not isinstance(storage_key, str) or not _STORAGE_KEY.fullmatch(storage_key):
        raise InvalidStorageKey("Windows CA storage key is invalid")
    return storage_key


def _validated_path(storage_key: str) -> tuple[Path, str]:
    key = _validate_key(storage_key)
    root = _configured_root()
    candidate = root / key
    try:
        info = candidate.lstat()
    except FileNotFoundError:
        raise BundleNotFound("Windows CA bundle does not exist") from None
    except OSError:
        raise UnsafeStoragePath("Windows CA bundle path is unavailable") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise UnsafeStoragePath("Windows CA bundle path is unsafe")
    return candidate, key


def store_pem_bytes(pem_bytes: bytes) -> str:
    """Store bytes under a generated key using a durable, non-overwriting finalize."""
    if not isinstance(pem_bytes, bytes) or not pem_bytes:
        raise StorageWriteError("Windows CA bundle content is empty")
    root = _configured_root()
    storage_key = f"ca-{secrets.token_hex(16)}.pem"
    final_path = root / storage_key
    temp_path: Path | None = None
    fd: int | None = None
    try:
        for _ in range(5):
            temp_path = root / f"{_TEMP_PREFIX}{secrets.token_hex(16)}.tmp"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(temp_path, flags, 0o600)
            with os.fdopen(fd, "wb", closefd=True) as handle:
                fd = None
                handle.write(pem_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_path, 0o600)
            link_flags = {"follow_symlinks": False} if os.name != "nt" else {}
            os.link(temp_path, final_path, **link_flags)
            os.unlink(temp_path)
            temp_path = None
            return storage_key
        raise StorageWriteError("Unable to allocate a unique Windows CA storage key")
    except FileExistsError:
        raise StorageWriteError("Unable to finalize Windows CA bundle storage") from None
    except (OSError, CABundleStorageError):
        raise StorageWriteError("Unable to store Windows CA bundle") from None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                pass


def resolve_storage_path(storage_key: str) -> Path:
    """Return a validated internal path for a stored bundle."""
    path, _ = _validated_path(storage_key)
    return path


def bundle_exists(storage_key: str) -> bool:
    try:
        resolve_storage_path(storage_key)
        return True
    except BundleNotFound:
        return False


def delete_stored_bundle(storage_key: str) -> None:
    """Delete one validated bundle; callers enforce authorization/reference checks."""
    path, key = _validated_path(storage_key)
    root = _configured_root()
    root_fd: int | None = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        root_fd = os.open(root, flags)
        os.unlink(key, dir_fd=root_fd)
    except FileNotFoundError:
        raise BundleNotFound("Windows CA bundle does not exist") from None
    except OSError:
        raise StorageDeleteError("Unable to delete Windows CA bundle") from None
    finally:
        if root_fd is not None:
            os.close(root_fd)
