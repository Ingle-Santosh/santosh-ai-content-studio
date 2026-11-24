from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChapterSuggestion(BaseModel):
    timestamp: str = Field(min_length=4, max_length=12)
    title: str = Field(min_length=2, max_length=120)


class ThumbnailConcept(BaseModel):
    concept_name: str = Field(min_length=2, max_length=120)
    headline_text: str = Field(min_length=2, max_length=80)
    visual_composition: str = Field(min_length=5, max_length=400)
    color_palette: str = Field(default="Dark slate background with sky-blue and amber accents")


class YouTubeMetadataLLMOutput(BaseModel):
    title_options: list[str] = Field(min_length=3, max_length=6)
    recommended_title: str = Field(min_length=5, max_length=120)
    description: str = Field(min_length=30)
    chapters: list[ChapterSuggestion] = Field(min_length=1)
    tags: list[str] = Field(min_length=3, max_length=30)
    hashtags: list[str] = Field(default_factory=list, max_length=8)
    thumbnail_concepts: list[ThumbnailConcept] = Field(min_length=2, max_length=4)
    pinned_comment: str = Field(default="")


class YouTubeMetadataReport(BaseModel):
    project_id: str
    topic: str
    publishing_mode: Literal["MANUAL_ONLY"] = "MANUAL_ONLY"
    metadata: YouTubeMetadataLLMOutput
    metadata_json_artifact_id: str | None = None
    metadata_markdown_artifact_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SceneSequenceEntry(BaseModel):
    scene_number: int
    title: str
    start_timestamp: str
    end_timestamp: str
    duration_seconds: int
    visual_type: str
    related_script_section: str
    on_screen_text: str | None = None
    camera_or_screen_instructions: str | None = None
    transition_instructions: str | None = None
    linked_asset_paths: list[str] = Field(default_factory=list)


class AssetManifestEntry(BaseModel):
    artifact_id: str
    stage: str
    artifact_type: str
    name: str
    relative_path: str
    version: int
    status: str
    size_bytes: int
    checksum_sha256: str | None = None
    scene_number: int | None = None


class ProductionEditingNotesLLMOutput(BaseModel):
    editing_summary: str = Field(min_length=10)
    pacing_and_audio_notes: list[str] = Field(default_factory=list)
    b_roll_and_overlay_cues: list[str] = Field(default_factory=list)
    recording_checklist: list[str] = Field(default_factory=list)
    post_production_checklist: list[str] = Field(default_factory=list)


class ProductionPackageReport(BaseModel):
    project_id: str
    topic: str
    publishing_mode: Literal["MANUAL_ONLY"] = "MANUAL_ONLY"
    manual_publishing_notice: str = (
        "No automatic publishing takes place. Review the exported ZIP package and upload manually "
        "to YouTube Studio."
    )
    total_estimated_duration_seconds: int = 0
    scene_sequence: list[SceneSequenceEntry] = Field(default_factory=list)
    asset_manifest: list[AssetManifestEntry] = Field(default_factory=list)
    editing_notes: ProductionEditingNotesLLMOutput
    youtube_metadata: YouTubeMetadataLLMOutput | None = None
    production_notes_artifact_id: str | None = None
    manifest_artifact_id: str | None = None
    export_zip_artifact_id: str | None = None
    export_zip_relative_path: str | None = None
    export_zip_file_count: int = 0
    approval_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
