from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from content_studio.contracts.guidelines import ChannelGuidelinesConfig


class ChannelGuidelineUpsertRequest(BaseModel):
    channel_name: str = Field(default="Santosh Analytics", min_length=1, max_length=255)
    is_active: bool = True
    guidelines: ChannelGuidelinesConfig = Field(default_factory=ChannelGuidelinesConfig)


class ChannelGuidelineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    channel_name: str
    is_active: bool
    guidelines_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ChannelGuidelineListResponse(BaseModel):
    items: list[ChannelGuidelineResponse]
    total: int
