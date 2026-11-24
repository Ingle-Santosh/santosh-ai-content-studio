from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from content_studio.database.models.claim import Claim
from content_studio.database.models.claim_source import ClaimSource
from content_studio.database.models.enums import ClaimVerdict, EvidenceStance, RiskLevel


class FactCheckRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_claim(
        self,
        *,
        project_id: str,
        statement: str,
        verdict: ClaimVerdict | str,
        confidence: float = 0.5,
        risk_level: RiskLevel | str = RiskLevel.MEDIUM,
        rationale: str = "",
        evidence_summary: str | None = None,
        run_id: str | None = None,
        finding_id: str | None = None,
    ) -> Claim:
        claim = Claim(
            project_id=project_id,
            run_id=run_id,
            finding_id=finding_id,
            statement=statement,
            verdict=verdict.value if isinstance(verdict, ClaimVerdict) else verdict,
            confidence=confidence,
            risk_level=risk_level.value if isinstance(risk_level, RiskLevel) else risk_level,
            rationale=rationale,
            evidence_summary=evidence_summary,
        )
        self._session.add(claim)
        await self._session.commit()
        await self._session.refresh(claim)
        return claim

    async def link_claim_source(
        self,
        *,
        claim_id: str,
        source_id: str,
        stance: EvidenceStance | str = EvidenceStance.SUPPORTS,
        excerpt: str | None = None,
    ) -> ClaimSource:
        link = ClaimSource(
            claim_id=claim_id,
            source_id=source_id,
            stance=stance.value if isinstance(stance, EvidenceStance) else stance,
            excerpt=excerpt,
        )
        self._session.add(link)
        await self._session.commit()
        await self._session.refresh(link)
        return link

    async def list_claims(
        self,
        project_id: str,
        *,
        verdict: ClaimVerdict | str | None = None,
    ) -> Sequence[Claim]:
        stmt = (
            select(Claim)
            .options(selectinload(Claim.claim_sources))
            .where(Claim.project_id == project_id)
            .order_by(Claim.created_at.desc())
        )
        if verdict is not None:
            verdict_val = verdict.value if isinstance(verdict, ClaimVerdict) else verdict
            stmt = stmt.where(Claim.verdict == verdict_val)
        result = await self._session.execute(stmt)
        return result.scalars().all()
