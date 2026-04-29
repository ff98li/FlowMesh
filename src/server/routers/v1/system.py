from typing import Any

from fastapi import APIRouter, Depends

from ...app_state import get_metrics
from ...services.metrics import MetricsRecorder

router = APIRouter(prefix="/system", tags=["System"])


@router.get(
    "/metrics",
    summary="Get metrics",
    description="Get a system metrics snapshot.",
    response_description="Metrics data",
)
async def get_metrics_snapshot(
    metrics: MetricsRecorder = Depends(get_metrics),
) -> dict[str, Any]:
    return metrics.snapshot()
