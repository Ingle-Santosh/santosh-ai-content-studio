from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from content_studio.contracts.storyboard import GeneratedStoryboardReport


class StoryboardGenerateRequest(BaseModel):
    script_version_number: int | None = Field(default=None, ge=1)
    require_approved_script: bool = True
    run_id: str | None = None


class SceneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    script_version_id: str | None
    run_id: str | None
    scene_number: int
    title: str
    estimated_duration_seconds: int
    narration: str
    on_screen_text: str | None
    visual_type: str
    asset_requirements_json: list[dict[str, Any]]
    camera_or_screen_instructions: str | None
    transition_instructions: str | None
    related_script_section: str
    created_at: datetime


class SceneListResponse(BaseModel):
    items: list[SceneResponse]
    total: int


StoryboardGenerateResponse = GeneratedStoryboardReport
