from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.database.models.enums import FindingCategory, SourceStatus
from content_studio.database.models.research_document import ResearchDocument
from content_studio.database.models.research_finding import ResearchFinding
from content_studio.database.models.source import Source


class ResearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_source_by_url_hash(self, project_id: str, url_hash: str) -> Source | None:
        stmt = select(Source).where(
            Source.project_id == project_id,
            Source.url_hash == url_hash,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_source(
        self,
        *,
        project_id: str,
        url: str,
        normalized_url: str,
        url_hash: str,
        title: str,
        domain: str,
        provider: str,
        snippet: str | None = None,
        status: SourceStatus | str = SourceStatus.DISCOVERED,
    ) -> Source:
        source = Source(
            project_id=project_id,
            url=url,
            normalized_url=normalized_url,
            url_hash=url_hash,
            title=title[:500],
            domain=domain[:255],
            snippet=snippet,
            provider=provider,
            status=status.value if isinstance(status, SourceStatus) else status,
        )
        self._session.add(source)
        await self._session.commit()
        await self._session.refresh(source)
        return source

    async def update_source(
        self,
        source: Source,
        *,
        status: SourceStatus | str | None = None,
        title: str | None = None,
        http_status: int | None = None,
        error_message: str | None = None,
    ) -> Source:
        if status is not None:
            source.status = status.value if isinstance(status, SourceStatus) else status
        if title:
            source.title = title[:500]
        if http_status is not None:
            source.http_status = http_status
        if error_message is not None:
            source.error_message = error_message
        source.updated_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(source)
        return source

    async def list_sources(
        self,
        project_id: str,
        *,
        status: SourceStatus | str | None = None,
    ) -> Sequence[Source]:
        stmt = (
            select(Source).where(Source.project_id == project_id).order_by(Source.created_at.desc())
        )
        if status is not None:
            status_val = status.value if isinstance(status, SourceStatus) else status
            stmt = stmt.where(Source.status == status_val)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_document_by_checksum(
        self,
        project_id: str,
        checksum_sha256: str,
    ) -> ResearchDocument | None:
        stmt = (
            select(ResearchDocument)
            .where(
                ResearchDocument.project_id == project_id,
                ResearchDocument.content_checksum_sha256 == checksum_sha256,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_document(
        self,
        *,
        project_id: str,
        source_id: str,
        artifact_id: str | None = None,
        title: str | None = None,
        author: str | None = None,
        published_date: str | None = None,
        language: str | None = None,
        word_count: int = 0,
        content_checksum_sha256: str | None = None,
        excerpt: str | None = None,
        extraction_method: str = "trafilatura",
        extraction_error: str | None = None,
    ) -> ResearchDocument:
        doc = ResearchDocument(
            project_id=project_id,
            source_id=source_id,
            artifact_id=artifact_id,
            title=title[:500] if title else None,
            author=author[:255] if author else None,
            published_date=published_date[:50] if published_date else None,
            language=language[:20] if language else None,
            word_count=word_count,
            content_checksum_sha256=content_checksum_sha256,
            excerpt=excerpt,
            extraction_method=extraction_method,
            extraction_error=extraction_error,
        )
        self._session.add(doc)
        await self._session.commit()
        await self._session.refresh(doc)
        return doc

    async def list_documents(self, project_id: str) -> Sequence[ResearchDocument]:
        stmt = (
            select(ResearchDocument)
            .where(ResearchDocument.project_id == project_id)
            .order_by(ResearchDocument.extracted_at.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def create_finding(
        self,
        *,
        project_id: str,
        title: str,
        summary: str,
        source_urls: list[str],
        source_id: str | None = None,
        run_id: str | None = None,
        category: FindingCategory | str = FindingCategory.FACT,
        confidence: float = 0.8,
        is_contradiction: bool = False,
    ) -> ResearchFinding:
        finding = ResearchFinding(
            project_id=project_id,
            source_id=source_id,
            run_id=run_id,
            category=category.value if isinstance(category, FindingCategory) else category,
            title=title[:300],
            summary=summary,
            source_urls_json=source_urls,
            confidence=confidence,
            is_contradiction=is_contradiction,
        )
        self._session.add(finding)
        await self._session.commit()
        await self._session.refresh(finding)
        return finding

    async def list_findings(
        self,
        project_id: str,
        *,
        category: FindingCategory | str | None = None,
    ) -> Sequence[ResearchFinding]:
        stmt = (
            select(ResearchFinding)
            .where(ResearchFinding.project_id == project_id)
            .order_by(ResearchFinding.created_at.desc())
        )
        if category is not None:
            cat_val = category.value if isinstance(category, FindingCategory) else category
            stmt = stmt.where(ResearchFinding.category == cat_val)
        result = await self._session.execute(stmt)
        return result.scalars().all()
