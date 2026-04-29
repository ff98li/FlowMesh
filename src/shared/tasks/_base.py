from pydantic import BaseModel, ConfigDict


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", from_attributes=True, populate_by_name=True
    )


class TemplateBaseModel(BaseModel):
    """
    Template-time base model.

    Still forbids unknown keys, but allows placeholder-friendly scalar types
    (e.g. int | "${...}") in *explicit* fields of concrete models.
    """

    model_config = ConfigDict(
        extra="forbid", from_attributes=True, populate_by_name=True
    )
