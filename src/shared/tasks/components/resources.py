from .._base import StrictBaseModel


class GPURequirements(StrictBaseModel):
    count: int | None = None
    type: str | None = None
    memory: str | int | float | None = None


class HardwareRequirements(StrictBaseModel):
    cpu: int | None = None
    memory: str | int | float | None = None
    gpu: GPURequirements | None = None


class ResourcesSpec(StrictBaseModel):
    estimatedLoad: int | None = None
    replicas: int | None = None
    hardware: HardwareRequirements | None = None
