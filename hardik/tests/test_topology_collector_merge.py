from backend.api.snmp_device_routes import _merge_collector_topology


def _baseline():
    devices = [{"id": str(i), "hostname": f"device-{i}"} for i in range(50)]
    links = [{"id": f"link-{i}", "from": "0", "to": str(i + 1), "localPort": str(i + 1)} for i in range(55)]
    return devices, links


def test_incomplete_collector_preserves_baseline():
    devices, links = _baseline()
    merged_devices, merged_links = _merge_collector_topology(devices, links, devices[:49], links[:48])
    assert len(merged_devices) == 50
    assert len(merged_links) == 55


def test_collector_adds_new_device_and_link():
    devices, links = _baseline()
    merged_devices, merged_links = _merge_collector_topology(
        devices, links,
        [{"id": "new-device", "hostname": "new"}],
        [{"id": "new-link", "from": "0", "to": "new-device", "localPort": "56"}],
    )
    assert any(item["id"] == "new-device" for item in merged_devices)
    assert any(item["id"] == "new-link" for item in merged_links)


def test_collector_updates_existing_metadata_without_replacing_graph():
    devices, links = _baseline()
    merged_devices, merged_links = _merge_collector_topology(
        devices, links,
        [{"id": "1", "hostname": "renamed", "status": "online"}],
        [{"id": "link-1", "from": "0", "to": "2", "localPort": "2", "status": "up"}],
    )
    assert len(merged_devices) == 50
    assert len(merged_links) == 55
    assert next(item for item in merged_devices if item["id"] == "1")["hostname"] == "renamed"
    assert next(item for item in merged_links if item["id"] == "link-1")["status"] == "up"


def test_empty_collector_cycle_does_not_delete_topology():
    devices, links = _baseline()
    assert _merge_collector_topology(devices, links, [], []) == (devices, links)


def test_only_explicit_positive_removal_deletes_entity_and_link():
    devices, links = _baseline()
    merged_devices, merged_links = _merge_collector_topology(
        devices,
        links,
        [{"id": "1", "removed": True}],
        [{"id": "link-1", "from": "0", "to": "2", "localPort": "2", "removed": True}],
    )
    assert not any(item["id"] == "1" for item in merged_devices)
    assert not any(item["id"] == "link-1" for item in merged_links)
    assert len(merged_devices) == 49
    assert len(merged_links) == 54
