import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.windows_monitoring import ca_bundle_storage as storage


@pytest.fixture
def configured_root(tmp_path, monkeypatch):
    root = tmp_path / "private-ca"
    root.mkdir()
    root.chmod(0o700)
    monkeypatch.setattr(storage, "get_settings", lambda: SimpleNamespace(windows_ca_storage_root=str(root), windows_ca_trust_path="/unchanged/global-ca.pem"))
    return root


def test_store_resolve_and_delete_pem_bytes(configured_root):
    key = storage.store_pem_bytes(b"-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----\n")

    assert storage._STORAGE_KEY.fullmatch(key)
    path = storage.resolve_storage_path(key)
    assert path.parent == configured_root
    assert path.read_bytes().startswith(b"-----BEGIN CERTIFICATE-----")
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert storage.bundle_exists(key)
    storage.delete_stored_bundle(key)
    assert not storage.bundle_exists(key)


def test_storage_key_is_opaque_and_cannot_overwrite(configured_root):
    key = storage.store_pem_bytes(b"one")
    path = storage.resolve_storage_path(key)
    with pytest.raises(storage.InvalidStorageKey):
        storage._validate_key("../existing.pem")
    assert path.read_bytes() == b"one"
    assert key != "existing.pem"


def test_concurrent_writes_are_unique(configured_root):
    with ThreadPoolExecutor(max_workers=8) as pool:
        keys = list(pool.map(storage.store_pem_bytes, [b"pem"] * 32))
    assert len(keys) == len(set(keys)) == 32
    assert all(storage.bundle_exists(key) for key in keys)


@pytest.mark.parametrize("key", ["../x.pem", "/tmp/x.pem", "ca-not-a-uuid.pem", "ca-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.pem/child"])
def test_invalid_storage_keys_are_rejected(configured_root, key):
    with pytest.raises(storage.InvalidStorageKey):
        storage.resolve_storage_path(key)


def test_symlinked_root_is_rejected(tmp_path, monkeypatch):
    real = tmp_path / "real"
    real.mkdir()
    real.chmod(0o700)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    monkeypatch.setattr(storage, "get_settings", lambda: SimpleNamespace(windows_ca_storage_root=str(link)))
    with pytest.raises(storage.InvalidStorageConfiguration):
        storage.store_pem_bytes(b"pem")


def test_symlinked_bundle_is_rejected(configured_root, tmp_path):
    key = "ca-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.pem"
    target = tmp_path / "outside.pem"
    target.write_bytes(b"outside")
    (configured_root / key).symlink_to(target)
    with pytest.raises(storage.UnsafeStoragePath):
        storage.resolve_storage_path(key)
    with pytest.raises(storage.UnsafeStoragePath):
        storage.delete_stored_bundle(key)
    assert target.read_bytes() == b"outside"


def test_missing_or_invalid_root_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "get_settings", lambda: SimpleNamespace(windows_ca_storage_root=""))
    with pytest.raises(storage.InvalidStorageConfiguration):
        storage.store_pem_bytes(b"pem")

    root = tmp_path / "too-open"
    root.mkdir(mode=0o755)
    monkeypatch.setattr(storage, "get_settings", lambda: SimpleNamespace(windows_ca_storage_root=str(root)))
    with pytest.raises(storage.InvalidStorageConfiguration):
        storage.store_pem_bytes(b"pem")


def test_write_failure_cleans_temporary_file(configured_root, monkeypatch):
    original_link = storage.os.link

    def fail_link(*args, **kwargs):
        raise OSError("simulated finalize failure")

    monkeypatch.setattr(storage.os, "link", fail_link)
    with pytest.raises(storage.StorageWriteError):
        storage.store_pem_bytes(b"pem")
    assert list(configured_root.iterdir()) == []
    monkeypatch.setattr(storage.os, "link", original_link)


def test_storage_root_is_separate_from_global_trust_path(configured_root):
    settings = storage.get_settings()
    assert settings.windows_ca_trust_path == "/unchanged/global-ca.pem"
    assert Path(settings.windows_ca_storage_root) == configured_root
