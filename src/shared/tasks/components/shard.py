from .._base import StrictBaseModel, TemplateBaseModel
from ..placeholders import TemplateBool, TemplateInt


class ShardSpec(StrictBaseModel):
    index: int
    total: int
    contiguous: bool | None = None


class ShardSpecTemplate(TemplateBaseModel):
    index: TemplateInt
    total: TemplateInt
    contiguous: TemplateBool | None = None
