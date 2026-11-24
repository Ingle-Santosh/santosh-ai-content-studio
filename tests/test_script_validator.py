from content_studio.contracts.script import ScriptSectionItem
from content_studio.database.models.enums import ScriptSectionType
from content_studio.services.script_validator import REQUIRED_SECTIONS, validate_script_sections


def _build_complete_sections() -> list[ScriptSectionItem]:
    return [
        ScriptSectionItem(
            section_type=sec_type,
            title=sec_type.value.replace("_", " ").title(),
            narration=(
                "Namaste dosto, aaj hum practical architecture aur step by step Python demo "
                "samjhenge jo real production systems mein kaam aata hai."
            ),
            visual_instructions="Face cam with architecture diagram overlay.",
            screen_recording_requirements=(
                "VS Code demo walkthrough"
                if sec_type == ScriptSectionType.PRACTICAL_DEMONSTRATION
                else None
            ),
            code_demo_references=(
                ["demo_rag.py"] if sec_type == ScriptSectionType.PRACTICAL_DEMONSTRATION else []
            ),
            estimated_duration_seconds=100,
            source_urls=["https://docs.example.com/rag"],
        )
        for sec_type in REQUIRED_SECTIONS
    ]


def test_script_validator_passes_complete_script() -> None:
    sections = _build_complete_sections()
    report = validate_script_sections(
        sections,
        target_duration_minutes=15,
        include_code_demo=True,
        known_source_urls={"https://docs.example.com/rag"},
        unsupported_claim_count=0,
    )
    assert report.passed is True
    assert report.score == 100.0
    assert report.errors == []
    assert report.warnings == []
    assert report.missing_sections == []


def test_script_validator_detects_missing_sections_and_warnings() -> None:
    incomplete = [
        ScriptSectionItem(
            section_type=ScriptSectionType.HOOK,
            title="Hook",
            narration="Short hook line here for testing.",
            visual_instructions="",
            estimated_duration_seconds=20,
            source_urls=["https://unverified.example.com/other"],
        )
    ]
    report = validate_script_sections(
        incomplete,
        target_duration_minutes=15,
        include_code_demo=True,
        known_source_urls={"https://docs.example.com/rag"},
        unsupported_claim_count=2,
    )
    assert report.passed is False
    assert len(report.missing_sections) == 8
    assert report.score < 50.0
    assert any("visual_instructions" in w for w in report.warnings)
    assert any("code_demo_references" in w for w in report.warnings)
    assert any("not present in extracted project sources" in w for w in report.warnings)
    assert any("unsupported/conflicting claim" in w for w in report.warnings)
