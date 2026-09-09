from backend.api.flow_routes import _source_selection_cte


def test_all_mode_applies_ipfix_precedence_without_deleting_raw_rows():
    sql = _source_selection_cte("f.flow_start >= :start", protocol_filtered=False)
    assert "ranked_flow_records" in sql
    assert "source_rank = 1" in sql
    assert "ipfix' AND c.quality = 'accounted' THEN 1" in sql
    assert "ipfix' AND c.quality = 'estimated' THEN 2" in sql
    assert "sflow' AND c.quality = 'estimated' THEN 3" in sql
    assert "COALESCE(c.device_id::text, c.exporter_ip)" in sql
    assert "FROM flow_records f" in sql


def test_explicit_protocol_filter_does_not_cross_select_other_sources():
    sql = _source_selection_cte("f.protocol = :protocol", protocol_filtered=True)
    assert "FROM flow_records f" in sql
    assert "ranked_flow_records" not in sql
    assert "WHERE f.protocol = :protocol" in sql


def test_quality_classification_keeps_unknown_sampling_unknown():
    sql = _source_selection_cte("TRUE", protocol_filtered=False)
    assert "ELSE 'unknown'" in sql
    assert "ELSE NULL" in sql
    assert "raw_fields -> 'ipfix' ->> 'sampled' = 'false'" in sql
