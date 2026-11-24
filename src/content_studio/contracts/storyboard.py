from datetime import UTC, datetime

from pydantic import BaseModel, Field

from content_studio.database.models.enums import SceneVisualType


class SceneAssetRequirement(BaseModel):
    asset_type: str = Field(min_length=2, max_length=50)
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="")


class StoryboardSceneItem(BaseModel):
    scene_number: int = Field(ge=1)
    title: str = Field(min_length=2, max_length=300)
    estimated_duration_seconds: int = Field(default=45, ge=5, le=1800)
    narration: str = Field(min_length=5)
    on_screen_text: str | None = None
    visual_type: SceneVisualType = SceneVisualType.FACE_CAM
    asset_requirements: list[SceneAssetRequirement] = Field(default_factory=list)
    camera_or_screen_instructions: str | None = None
    transition_instructions: str | None = None
    related_script_section: str = Field(default="")


class StoryboardLLMOutput(BaseModel):
    summary: str = Field(min_length=10)
    scenes: list[StoryboardSceneItem] = Field(min_length=1)


class GeneratedStoryboardReport(BaseModel):
    project_id: str
    script_version_id: str
    script_version_number: int
    summary: str
    total_scenes: int
    total_estimated_duration_seconds: int
    total_asset_requirements: int
    scenes: list[StoryboardSceneItem]
    storyboard_markdown_artifact_id: str | None = None
    storyboard_json_artifact_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
