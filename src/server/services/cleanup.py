import logging
import threading

from ..clients import RedisClient

_REDIS_FLUSH_LOCK = threading.Lock()
_REDIS_FLUSHED = False


def clear_redis_state(redis_client: RedisClient, logger: logging.Logger) -> None:
    global _REDIS_FLUSHED
    with _REDIS_FLUSH_LOCK:
        if _REDIS_FLUSHED:
            return
        try:
            redis_client.sync.flush_all()
            _REDIS_FLUSHED = True
        except Exception as exc:
            logger.warning("Failed to clear Redis database on exit: %s", exc)
