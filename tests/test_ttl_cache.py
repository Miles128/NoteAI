"""Tests for TTL cache."""

import time
import pytest
from utils.ttl_cache import TTLCache


class TestTTLCache:
    def test_set_and_get(self):
        c = TTLCache(ttl=60)
        c.set("a", 1)
        assert c.get("a") == 1

    def test_expiry(self):
        c = TTLCache(ttl=0.01)
        c.set("a", 1)
        time.sleep(0.02)
        assert c.get("a") is None

    def test_missing_key(self):
        c = TTLCache()
        assert c.get("nope") is None

    def test_delete(self):
        c = TTLCache()
        c.set("a", 1)
        assert c.delete("a") is True
        assert c.get("a") is None
        assert c.delete("a") is False

    def test_max_size_eviction(self):
        c = TTLCache(max_size=2, ttl=999)
        c.set("a", 1)
        c.set("b", 2)
        c.set("c", 3)
        assert c.get("a") is None  # oldest evicted
        assert c.get("b") == 2
        assert c.get("c") == 3

    def test_clear(self):
        c = TTLCache()
        c.set("a", 1)
        c.set("b", 2)
        c.clear()
        assert c.get("a") is None
        assert c.get("b") is None
        assert len(c) == 0

    def test_contains(self):
        c = TTLCache()
        assert "a" not in c
        c.set("a", 1)
        assert "a" in c

    def test_expire_removes_expired(self):
        c = TTLCache(ttl=0.01)
        c.set("a", 1)
        c.set("b", 2, ttl=999)
        time.sleep(0.02)
        removed = c.expire()
        assert removed == 1
        assert c.get("a") is None
        assert c.get("b") == 2
