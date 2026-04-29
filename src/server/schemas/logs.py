from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class LogStream(StrEnum):
    STDOUT = "stdout"
    STDERR = "stderr"
    SYSTEM = "system"


class LogEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str | None = Field(default=None, description="Event timestamp (ISO8601).")
    workflow_id: str | None = Field(default=None, description="Workflow identifier.")
    task_id: str | None = Field(default=None, description="Task identifier.")
    worker_id: str | None = Field(default=None, description="Worker identifier.")
    node_id: str | None = Field(default=None, description="Node identifier.")
    level: LogLevel | str | None = Field(default=None, description="Severity level.")
    stream: LogStream | str | None = Field(
        default=None, description="Log stream (stdout|stderr|system)."
    )
    source: str | None = Field(default=None, description="Subsystem identifier.")
    message: str | None = Field(default=None, description="Log message.")
    fields: dict[str, Any] | None = Field(
        default=None, description="Optional structured metadata."
    )


class LogEntry(BaseModel):
    cursor: str = Field(description="Log cursor.")
    event: LogEvent = Field(description="Log event payload.")


class LogQueryResponse(BaseModel):
    entries: list[LogEntry] = Field(description="Ordered log entries.")
    next_cursor: str | None = Field(
        default=None, description="Cursor for forward pagination."
    )
    prev_cursor: str | None = Field(
        default=None, description="Cursor for backward pagination."
    )
