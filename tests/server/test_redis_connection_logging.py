"""Redis connection failures redact credentials before logging."""

import logging

import pytest

from server.clients import redis as redis_client_module
from server.clients.redis import AsyncRedisClient, SyncRedisClient


_REDIS_URL = "redis://flowmesh:test-password@localhost:6379/0"
_REDACTED_URL = "redis://flowmesh:****@localhost:6379/0"


def _raise_connection_error(*args: object, **kwargs: object) -> None:
    raise ConnectionError(f"connection refused for {_REDIS_URL}")


def test_sync_connection_failure_redacts_credentials(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(redis_client_module, "_keepalive_kwargs", lambda: {})
    monkeypatch.setattr(redis_client_module.redis, "from_url", _raise_connection_error)
    logger = logging.getLogger("test.sync-redis-connection")

    with pytest.raises(SystemExit):
        SyncRedisClient(_REDIS_URL, _REDIS_URL, logger)

    assert _REDACTED_URL in caplog.text
    assert "ConnectionError" in caplog.text
    assert _REDIS_URL not in caplog.text
    assert "test-password" not in caplog.text


def test_async_connection_failure_redacts_credentials(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(redis_client_module, "_keepalive_kwargs", lambda: {})
    monkeypatch.setattr(
        redis_client_module.async_redis, "from_url", _raise_connection_error
    )
    logger = logging.getLogger("test.async-redis-connection")

    with pytest.raises(SystemExit):
        AsyncRedisClient(_REDIS_URL, _REDIS_URL, logger)

    assert _REDACTED_URL in caplog.text
    assert "ConnectionError" in caplog.text
    assert _REDIS_URL not in caplog.text
    assert "test-password" not in caplog.text
