"""Usage-sink hook.

Fan-out for per-task usage rows after a task completes. Each sink decides
which rows it consumes and how to deliver them. Sink failures are isolated by
the caller — they must not break the dispatch path.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Protocol, TypedDict, runtime_checkable


class UsageRow(TypedDict):
    org_id: str
    principal_id: str
    supplier_id: str | None
    occurred_at: datetime
    cost: Decimal
    task_id: str
    runtime_sec: float
    cost_per_hour: float
    task_status: str


@runtime_checkable
class UsageSink(Protocol):
    name: str

    async def emit(self, rows: list[UsageRow], logger: logging.Logger) -> None:
        """Deliver per-task usage rows to a downstream sink."""
        ...
