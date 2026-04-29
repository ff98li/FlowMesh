from dataclasses import dataclass, field

from ..agents.common import DataClassWithStreamEvents


@dataclass
class GeneratorTaskRecorder(DataClassWithStreamEvents):
    requirements: str | None = field(default=None)
    selected_tools: dict[str, list[str]] | None = field(default=None)
    instructions: str | None = field(default=None)
    name: str | None = field(default=None)
