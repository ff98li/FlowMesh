from typing import Literal

from ..placeholders import TemplateBool, TemplateInt
from ..task_type import TaskType
from .common import (
    ModelInferSpecStrict,
    ModelInferSpecTemplate,
    ParallelSpec,
    ParallelSpecTemplate,
)


class InferenceSpecStrict(ModelInferSpecStrict):
    taskType: Literal[TaskType.INFERENCE]

    sloSeconds: int | None = None
    parallel: ParallelSpec | None = None
    enforce_cpu: bool | None = None


class InferenceSpecTemplate(ModelInferSpecTemplate):
    taskType: Literal[TaskType.INFERENCE]

    sloSeconds: TemplateInt | None = None
    parallel: ParallelSpecTemplate | None = None
    enforce_cpu: TemplateBool | None = None
