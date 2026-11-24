from pydantic import BaseModel, Field


class ChannelGuidelinesConfig(BaseModel):
    """Structured channel guidelines for Santosh Analytics content production."""

    audience: str = "Beginners and intermediate technology learners"
    narration_language: str = "Hinglish"
    technical_terminology: str = "English"
    explanation_style: str = "Simple sentences and practical examples"
    presentation_style: str = "Show face, supported by screen recordings and visuals"
    core_topics: list[str] = Field(
        default_factory=lambda: [
            "Analytics",
            "Data Science",
            "Machine Learning",
            "GenAI",
            "Agentic AI",
            "MLOps",
            "SQL",
            "Cloud",
        ]
    )
    visual_standards: str = "Professional diagrams, animations, screenshots and executable code"
    tutorial_approach: str = "Practical, step-by-step demonstrations"
    creator_bio_note: str = "Mention 8+ years of experience in the data field"
    publishing_mode: str = "Manual review and upload"
    extra_rules: list[str] = Field(default_factory=list)
