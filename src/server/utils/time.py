import datetime
import time

from shared.utils.time import now_iso


def parse_iso_ts(value: str | None) -> float:
    if not value:
        return time.time()
    try:
        v = value
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        return datetime.datetime.fromisoformat(v).timestamp()
    except Exception:
        return time.time()


__all__ = ["now_iso", "parse_iso_ts"]
