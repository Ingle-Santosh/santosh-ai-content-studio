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


class AgentRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ApprovalGate(StrEnum):
    BRIEF = "brief"
    RESEARCH = "research"
    SCRIPT = "script"
    STORYBOARD_ASSETS = "storyboard_assets"
    PRODUCTION_PACKAGE = "production_package"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"


class SourceStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    EXTRACTED = "EXTRACTED"
    DUPLICATE = "DUPLICATE"
    FAILED = "FAILED"


class FindingCategory(StrEnum):
    CONCEPT = "concept"
    FACT = "fact"
    DEFINITION = "definition"
    EXAMPLE = "example"
    BEST_PRACTICE = "best_practice"
    CONTRADICTION = "contradiction"
    STATISTIC = "statistic"


class ArtifactType(StrEnum):
    CONTENT_BRIEF = "content_brief"
    RESEARCH_BRIEF = "research_brief"
    FACT_CHECK_REPORT = "fact_check_report"
    COMPETITOR_REPORT = "competitor_report"
    OUTLINE = "outline"
    SCRIPT = "script"
    STORYBOARD = "storyboard"
    DIAGRAM_MMD = "diagram_mmd"
    DIAGRAM_SVG = "diagram_svg"
    DIAGRAM_PNG = "diagram_png"
    HTML_ANIMATION = "html_animation"
    IMAGE = "image"
    SCREENSHOT = "screenshot"
    CODE_DEMO = "code_demo"
    QA_REVIEW = "qa_review"
    YOUTUBE_METADATA = "youtube_metadata"
    EXPORT_BUNDLE = "export_bundle"
    OTHER = "other"


class ArtifactStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"
