"""Redis connection failures redact credentials before logging."""

import logging

import pytest

from server.clients import redis as redis_client_module
from server.clients.redis import AsyncRedisClient, SyncRedisClient


_REDIS_URL = "redis://flowmesh:test-password@localhost:6379/0"
_REDACTED_URL = "redis://flowmesh:****@localhost:6379/0"


def _raise_connection_error(*args: object, **kwargs: object) -> None:
    raise ConnectionError(f"connection refused for {_REDIS_URL}")


class _SyncPingFailure:
    def ping(self) -> None:
        raise ConnectionError(f"connection refused for {_REDIS_URL}")


class _SyncFlushClient:
    def flushdb(self) -> None:
        return None


class _AsyncFlushClient:
    async def flushdb(self) -> None:
        return None


def _assert_secret_absent(caplog: pytest.LogCaptureFixture) -> None:
    assert _REDACTED_URL in caplog.text
    assert _REDIS_URL not in caplog.text
    assert "test-password" not in caplog.text


def test_sync_connection_failure_redacts_credentials(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(redis_client_module, "_keepalive_kwargs", lambda: {})
    monkeypatch.setattr(redis_client_module.redis, "from_url", _raise_connection_error)
    logger = logging.getLogger("test.sync-redis-connection")

    with pytest.raises(SystemExit) as caught:
        SyncRedisClient(_REDIS_URL, _REDIS_URL, logger)

    assert caught.value.__context__ is None
    assert "ConnectionError" in caplog.text
    _assert_secret_absent(caplog)


def test_sync_ping_failure_redacts_credentials(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(redis_client_module, "_keepalive_kwargs", lambda: {})
    monkeypatch.setattr(
        redis_client_module.redis,
        "from_url",
        lambda *args, **kwargs: _SyncPingFailure(),
    )
    logger = logging.getLogger("test.sync-redis-ping")

    with pytest.raises(SystemExit) as caught:
        SyncRedisClient(_REDIS_URL, _REDIS_URL, logger)

    assert caught.value.__context__ is None
    assert "ConnectionError" in caplog.text
    _assert_secret_absent(caplog)


def test_async_connection_failure_redacts_credentials(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(redis_client_module, "_keepalive_kwargs", lambda: {})
    monkeypatch.setattr(
        redis_client_module.async_redis, "from_url", _raise_connection_error
    )
    logger = logging.getLogger("test.async-redis-connection")

    with pytest.raises(SystemExit) as caught:
        AsyncRedisClient(_REDIS_URL, _REDIS_URL, logger)

    assert caught.value.__context__ is None
    assert "ConnectionError" in caplog.text
    _assert_secret_absent(caplog)


def test_sync_flush_logs_redacted_urls(caplog: pytest.LogCaptureFixture) -> None:
    client = SyncRedisClient.__new__(SyncRedisClient)
    client.control_url = _REDIS_URL
    client.telemetry_url = _REDIS_URL
    client.logger = logging.getLogger("test.sync-redis-flush")
    client._control = _SyncFlushClient()  # type: ignore[assignment]
    client._telemetry = _SyncFlushClient()  # type: ignore[assignment]

    client.flush_all()

    _assert_secret_absent(caplog)


@pytest.mark.anyio
async def test_async_flush_logs_redacted_urls(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = AsyncRedisClient.__new__(AsyncRedisClient)
    client.control_url = _REDIS_URL
    client.telemetry_url = _REDIS_URL
    client.logger = logging.getLogger("test.async-redis-flush")
    client._control = _AsyncFlushClient()  # type: ignore[assignment]
    client._telemetry = _AsyncFlushClient()  # type: ignore[assignment]

    await client.flush_all()

    _assert_secret_absent(caplog)
