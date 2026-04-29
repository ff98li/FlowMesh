from ._base import StrictBaseModel
from .components import TaskMetadata
from .envelope import TaskSpecStrict


class MergedChildTaskStrict(StrictBaseModel):
    task_id: str
    owner_id: str
    workflow_id: str
    spec: TaskSpecStrict
    metadata: TaskMetadata | None = None
