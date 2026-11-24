import contextlib

from content_studio.contracts.script import ScriptSectionItem, ScriptValidationReport
from content_studio.database.models.enums import ScriptSectionType
from content_studio.services.web_extractor import normalize_url

REQUIRED_SECTIONS: tuple[ScriptSectionType, ...] = (
    ScriptSectionType.HOOK,
    ScriptSectionType.INTRODUCTION,
    ScriptSectionType.PROBLEM_STATEMENT,
    ScriptSectionType.LEARNING_OBJECTIVES,
    ScriptSectionType.MAIN_EXPLANATION,
    ScriptSectionType.PRACTICAL_DEMONSTRATION,
    ScriptSectionType.EXAMPLES,
    ScriptSectionType.SUMMARY,
    ScriptSectionType.CALL_TO_ACTION,
)


def validate_script_sections(
    sections: list[ScriptSectionItem],
    *,
    target_duration_minutes: int = 15,
    include_code_demo: bool = True,
    known_source_urls: set[str] | None = None,
    unsupported_claim_count: int = 0,
) -> ScriptValidationReport:
    """Deterministic validation of script completeness, pacing, visuals, and citations."""
    errors: list[str] = []
    warnings: list[str] = []

    present_types = {section.section_type for section in sections}
    missing = [sec.value for sec in REQUIRED_SECTIONS if sec not in present_types]
    if missing:
        errors.append(f"Missing required script sections: {', '.join(missing)}.")

    total_words = 0
    total_duration = 0
    has_code_reference = False
    missing_visuals_count = 0

    normalized_known: set[str] = set()
    if known_source_urls:
        for url in known_source_urls:
            normalized_known.add(url.strip())
            with contextlib.suppress(ValueError):
                normalized_known.add(normalize_url(url))

    unknown_urls: list[str] = []

    for section in sections:
        words = len(section.narration.split())
        total_words += words
        total_duration += section.estimated_duration_seconds

        if words < 10:
            warnings.append(
                f"Section '{section.section_type.value}' narration is very short ({words} words)."
            )
        if not section.visual_instructions.strip():
            missing_visuals_count += 1
        if section.code_demo_references or section.screen_recording_requirements:
            has_code_reference = True

        if normalized_known:
            for url in section.source_urls:
                cleaned = url.strip()
                matched = cleaned in normalized_known
                if not matched:
                    try:
                        matched = normalize_url(cleaned) in normalized_known
                    except ValueError:
                        matched = False
                if not matched:
                    unknown_urls.append(cleaned)

    if missing_visuals_count > 0:
        warnings.append(f"{missing_visuals_count} section(s) are missing visual_instructions.")

    if include_code_demo and not has_code_reference:
        warnings.append(
            "Project enables code demos, but no section lists code_demo_references or "
            "screen_recording_requirements."
        )

    target_seconds = target_duration_minutes * 60
    if total_duration < int(target_seconds * 0.5):
        warnings.append(
            f"Estimated duration ({total_duration}s) is significantly shorter than target "
            f"({target_seconds}s)."
        )
    elif total_duration > int(target_seconds * 1.5):
        warnings.append(
            f"Estimated duration ({total_duration}s) significantly exceeds target "
            f"({target_seconds}s)."
        )

    if unknown_urls:
        warnings.append(
            f"Script cites {len(unknown_urls)} source URL(s) not present in extracted project "
            f"sources: {', '.join(unknown_urls[:3])}"
        )

    if unsupported_claim_count > 0:
        warnings.append(
            f"{unsupported_claim_count} unsupported/conflicting claim(s) exist in fact-check; "
            "verify narration does not state them as established fact."
        )

    score = 100.0
    score -= len(missing) * 8.0
    score -= min(missing_visuals_count * 4.0, 20.0)
    score -= min(len(warnings) * 5.0, 25.0)
    score = max(0.0, min(100.0, round(score, 1)))

    return ScriptValidationReport(
        passed=len(errors) == 0,
        score=score,
        errors=errors,
        warnings=warnings,
        missing_sections=missing,
        total_words=total_words,
        total_duration_seconds=total_duration,
        target_duration_seconds=target_seconds,
    )
