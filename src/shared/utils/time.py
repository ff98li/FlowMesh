import datetime


def now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()
