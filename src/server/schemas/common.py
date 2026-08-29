from pydantic import BaseModel, Field


class OkResponse(BaseModel):
    ok: bool = Field(description="Whether the request succeeded.")


class ReadinessResponse(OkResponse):
    checks: dict[str, bool] = Field(description="Dependency readiness by component.")
    details: dict[str, str] = Field(
        default_factory=dict, description="Secret-free readiness context."
    )


class VersionResponse(BaseModel):
    version: str = Field(description="Server version.")


class PathResponse(OkResponse):
    path: str = Field(description="Filesystem path of the stored artifact.")
