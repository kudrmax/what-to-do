from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model
from pydantic.fields import FieldInfo


class AppSettings(BaseModel):
    """Every setting of the app, described once: storage, the API and its change request all come from here."""

    model_config = ConfigDict(extra="ignore")

    active_city_id: int | None = Field(default=None, description="null until the first city is added")
    description_language: str = Field(default="русский", min_length=1, description="Language Claude writes titles and descriptions in")
    recent_posts: int = Field(
        default=20,
        ge=1,
        le=300,
        description="How many latest posts of every channel are read; raising it reads older posts on the next refresh",
    )


def _optional(info: FieldInfo) -> tuple[Any, FieldInfo]:
    return info.annotation | None, FieldInfo.merge_field_infos(info, default=None)


SettingsChange = create_model(
    "SettingsChange",
    __doc__="Only the fields that are sent change.",
    **{name: _optional(info) for name, info in AppSettings.model_fields.items()},
)
