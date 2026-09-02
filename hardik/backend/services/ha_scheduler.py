"""Redis lease used to ensure one monitoring scheduler per deployment."""
from __future__ import annotations
import os, uuid
from backend.cache.redis_cache import _get_client
from backend.config.settings import get_settings
class SchedulerLease:
    def __init__(self, key="nms:scheduler:leader", ttl=30): self.key=key; self.ttl=ttl; self.token=f"{os.getpid()}:{uuid.uuid4()}"; self.client=_get_client()
    def acquire(self):
        if self.client is None: return get_settings().environment != "production"
        try: return bool(self.client.set(self.key,self.token,nx=True,ex=self.ttl))
        except Exception: return False
    def renew(self):
        if not self.client: return get_settings().environment != "production"
        try: return self.client.get(self.key)==self.token and bool(self.client.expire(self.key,self.ttl))
        except Exception: return False
    def release(self):
        if not self.client:return
        try:
            if self.client.get(self.key)==self.token:self.client.delete(self.key)
        except Exception: pass
