from fastapi import APIRouter

from ..schemas.common import OkResponse

router = APIRouter(tags=["Health", "Caller: anyone"])


@router.get(
    "/healthz",
    summary="Health check",
    description="Service health check.",
    response_description="Health status",
)
async def healthz() -> OkResponse:
    return OkResponse(ok=True)
