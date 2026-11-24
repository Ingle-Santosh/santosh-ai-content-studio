from enum import StrEnum


class ProjectStatus(StrEnum):
    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    INTERRUPTED = "INTERRUPTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ArtifactType(StrEnum):
    RESEARCH_BRIEF = "research_brief"
    OUTLINE = "outline"
    SCRIPT = "script"
    DIAGRAM_MMD = "diagram_mmd"
    DIAGRAM_SVG = "diagram_svg"
    DIAGRAM_PNG = "diagram_png"
    HTML_ANIMATION = "html_animation"
    CODE_DEMO = "code_demo"
    QA_REVIEW = "qa_review"
    EXPORT_BUNDLE = "export_bundle"


class ArtifactStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"
