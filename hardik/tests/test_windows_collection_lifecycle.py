from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from backend.windows_monitoring.collection_lifecycle import CollectionState
from backend.windows_monitoring.models import WindowsProcessCollection


def test_lifecycle_states_are_explicit_and_terminal_states_are_immutable():
    assert {state.value for state in CollectionState} == {"RESERVED", "COLLECTING", "FINALIZED", "FAILED", "SUPERSEDED", "EXPIRED"}
    assert WindowsProcessCollection.__table__.name == "windows_process_collections"
    assert WindowsProcessCollection.__table__.c.collection_id.unique is True
