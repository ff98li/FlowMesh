from enum import StrEnum


class WorkerStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    STARTING = "STARTING"
    IDLE = "IDLE"
    BUSY = "BUSY"


__all__ = ["WorkerStatus"]
