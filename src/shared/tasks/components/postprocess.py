from typing import Any

from .._base import StrictBaseModel, TemplateBaseModel


class JsonlExportSpec(StrictBaseModel):
    path: str
    fields: dict[str, Any]
    required_fields: list[str] | None = None


class JsonlExportSpecTemplate(TemplateBaseModel):
    path: str
    fields: dict[str, Any]
    required_fields: list[str] | None = None


class PostprocessSpec(StrictBaseModel):
    jsonl_export: JsonlExportSpec | None = None


class PostprocessSpecTemplate(TemplateBaseModel):
    jsonl_export: JsonlExportSpecTemplate | None = None
