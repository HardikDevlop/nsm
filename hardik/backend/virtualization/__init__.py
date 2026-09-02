from typing import Protocol
class VirtualizationAdapter(Protocol):
    provider: str
    def inventory(self) -> list[dict]: ...
ADAPTERS = {}
def register_adapter(adapter): ADAPTERS[adapter.provider] = adapter
def get_adapter(provider): return ADAPTERS.get(provider)
