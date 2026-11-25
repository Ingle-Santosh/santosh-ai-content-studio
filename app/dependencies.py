from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.config.settings import Settings, settings
from content_studio.database.repositories import (
    AgentRunRepository,
    ApprovalRepository,
    ArtifactRepository,
    ChannelGuidelineRepository,
    CompetitorRepository,
    EvaluationRepository,
    FactCheckRepository,
    ModelRegistryRepository,
    ProjectRepository,
    ResearchRepository,
    RunRepository,
    SceneRepository,
    ScriptRepository,
    UsageRepository,
)
from content_studio.database.session import get_db_session
from content_studio.evaluation import EvaluationService
from content_studio.providers.image import BaseImageProvider, LocalSVGImageProvider
from content_studio.providers.llm import ModelRouter
from content_studio.providers.search import BaseSearchProvider, build_search_provider
from content_studio.providers.youtube import BaseYouTubeProvider, build_youtube_provider
from content_studio.services import (
    ApprovalService,
    ArtifactService,
    AssetGenerationService,
    AssetQAService,
    ChannelGuidelineService,
    CompetitorService,
    FactCheckService,
    ModelRegistryService,
    ProductionService,
    ResearchService,
    ScriptwriterService,
    StoryboardService,
    TopicStrategistService,
    WebExtractor,
    YouTubeStrategyService,
)
from content_studio.storage.artifact_store import ArtifactStore
from content_studio.workflows import PipelineServices, WorkflowOrchestrator


def get_settings() -> Settings:
    return settings


def get_artifact_store(
    app_settings: Annotated[Settings, Depends(get_settings)],
) -> ArtifactStore:
    return ArtifactStore(projects_dir=app_settings.resolved_projects_dir)


def get_project_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectRepository:
    return ProjectRepository(session)


def get_artifact_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ArtifactRepository:
    return ArtifactRepository(session)


def get_run_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RunRepository:
    return RunRepository(session)


def get_usage_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UsageRepository:
    return UsageRepository(session)


def get_approval_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApprovalRepository:
    return ApprovalRepository(session)


def get_guideline_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChannelGuidelineRepository:
    return ChannelGuidelineRepository(session)


def get_agent_run_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentRunRepository:
    return AgentRunRepository(session)


def get_research_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResearchRepository:
    return ResearchRepository(session)


def get_fact_check_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FactCheckRepository:
    return FactCheckRepository(session)


def get_competitor_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CompetitorRepository:
    return CompetitorRepository(session)


def get_script_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ScriptRepository:
    return ScriptRepository(session)


def get_scene_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SceneRepository:
    return SceneRepository(session)


def get_evaluation_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EvaluationRepository:
    return EvaluationRepository(session)


def get_model_registry_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ModelRegistryRepository:
    return ModelRegistryRepository(session)


def get_model_registry_service(
    app_settings: Annotated[Settings, Depends(get_settings)],
    registry_repo: Annotated[ModelRegistryRepository, Depends(get_model_registry_repository)],
) -> ModelRegistryService:
    return ModelRegistryService(
        app_settings=app_settings,
        registry_repo=registry_repo,
    )


def get_artifact_service(
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    artifact_repo: Annotated[ArtifactRepository, Depends(get_artifact_repository)],
    store: Annotated[ArtifactStore, Depends(get_artifact_store)],
) -> ArtifactService:
    return ArtifactService(
        project_repo=project_repo,
        artifact_repo=artifact_repo,
        store=store,
    )


def get_guideline_service(
    repo: Annotated[ChannelGuidelineRepository, Depends(get_guideline_repository)],
) -> ChannelGuidelineService:
    return ChannelGuidelineService(repo)


def get_approval_service(
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    approval_repo: Annotated[ApprovalRepository, Depends(get_approval_repository)],
    artifact_repo: Annotated[ArtifactRepository, Depends(get_artifact_repository)],
) -> ApprovalService:
    return ApprovalService(
        project_repo=project_repo,
        approval_repo=approval_repo,
        artifact_repo=artifact_repo,
    )


def get_model_router(
    app_settings: Annotated[Settings, Depends(get_settings)],
    usage_repo: Annotated[UsageRepository, Depends(get_usage_repository)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    registry_service: Annotated[ModelRegistryService, Depends(get_model_registry_service)],
) -> ModelRouter:
    return ModelRouter(
        app_settings=app_settings,
        usage_repo=usage_repo,
        project_repo=project_repo,
        registry_service=registry_service,
    )


def get_search_provider(
    app_settings: Annotated[Settings, Depends(get_settings)],
) -> BaseSearchProvider:
    return build_search_provider(app_settings)


def get_web_extractor(
    app_settings: Annotated[Settings, Depends(get_settings)],
) -> WebExtractor:
    return WebExtractor(timeout_seconds=app_settings.RESEARCH_FETCH_TIMEOUT_SECONDS)


def get_youtube_provider(
    app_settings: Annotated[Settings, Depends(get_settings)],
    search_provider: Annotated[BaseSearchProvider, Depends(get_search_provider)],
) -> BaseYouTubeProvider:
    return build_youtube_provider(app_settings, search_provider=search_provider)


def get_research_service(
    app_settings: Annotated[Settings, Depends(get_settings)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    research_repo: Annotated[ResearchRepository, Depends(get_research_repository)],
    artifact_service: Annotated[ArtifactService, Depends(get_artifact_service)],
    search_provider: Annotated[BaseSearchProvider, Depends(get_search_provider)],
    extractor: Annotated[WebExtractor, Depends(get_web_extractor)],
    model_router: Annotated[ModelRouter, Depends(get_model_router)],
    agent_run_repo: Annotated[AgentRunRepository, Depends(get_agent_run_repository)],
) -> ResearchService:
    return ResearchService(
        app_settings=app_settings,
        project_repo=project_repo,
        research_repo=research_repo,
        artifact_service=artifact_service,
        search_provider=search_provider,
        extractor=extractor,
        model_router=model_router,
        agent_run_repo=agent_run_repo,
    )


def get_fact_check_service(
    app_settings: Annotated[Settings, Depends(get_settings)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    research_repo: Annotated[ResearchRepository, Depends(get_research_repository)],
    fact_check_repo: Annotated[FactCheckRepository, Depends(get_fact_check_repository)],
    artifact_service: Annotated[ArtifactService, Depends(get_artifact_service)],
    model_router: Annotated[ModelRouter, Depends(get_model_router)],
    approval_service: Annotated[ApprovalService, Depends(get_approval_service)],
    agent_run_repo: Annotated[AgentRunRepository, Depends(get_agent_run_repository)],
) -> FactCheckService:
    return FactCheckService(
        app_settings=app_settings,
        project_repo=project_repo,
        research_repo=research_repo,
        fact_check_repo=fact_check_repo,
        artifact_service=artifact_service,
        model_router=model_router,
        approval_service=approval_service,
        agent_run_repo=agent_run_repo,
    )


def get_competitor_service(
    app_settings: Annotated[Settings, Depends(get_settings)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    competitor_repo: Annotated[CompetitorRepository, Depends(get_competitor_repository)],
    artifact_service: Annotated[ArtifactService, Depends(get_artifact_service)],
    youtube_provider: Annotated[BaseYouTubeProvider, Depends(get_youtube_provider)],
    model_router: Annotated[ModelRouter, Depends(get_model_router)],
    agent_run_repo: Annotated[AgentRunRepository, Depends(get_agent_run_repository)],
) -> CompetitorService:
    return CompetitorService(
        app_settings=app_settings,
        project_repo=project_repo,
        competitor_repo=competitor_repo,
        artifact_service=artifact_service,
        youtube_provider=youtube_provider,
        model_router=model_router,
        agent_run_repo=agent_run_repo,
    )


def get_scriptwriter_service(
    app_settings: Annotated[Settings, Depends(get_settings)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    script_repo: Annotated[ScriptRepository, Depends(get_script_repository)],
    research_repo: Annotated[ResearchRepository, Depends(get_research_repository)],
    fact_check_repo: Annotated[FactCheckRepository, Depends(get_fact_check_repository)],
    competitor_repo: Annotated[CompetitorRepository, Depends(get_competitor_repository)],
    guideline_service: Annotated[ChannelGuidelineService, Depends(get_guideline_service)],
    artifact_service: Annotated[ArtifactService, Depends(get_artifact_service)],
    model_router: Annotated[ModelRouter, Depends(get_model_router)],
    approval_service: Annotated[ApprovalService, Depends(get_approval_service)],
    agent_run_repo: Annotated[AgentRunRepository, Depends(get_agent_run_repository)],
) -> ScriptwriterService:
    return ScriptwriterService(
        app_settings=app_settings,
        project_repo=project_repo,
        script_repo=script_repo,
        research_repo=research_repo,
        fact_check_repo=fact_check_repo,
        competitor_repo=competitor_repo,
        guideline_service=guideline_service,
        artifact_service=artifact_service,
        model_router=model_router,
        approval_service=approval_service,
        agent_run_repo=agent_run_repo,
    )


def get_storyboard_service(
    app_settings: Annotated[Settings, Depends(get_settings)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    script_repo: Annotated[ScriptRepository, Depends(get_script_repository)],
    scene_repo: Annotated[SceneRepository, Depends(get_scene_repository)],
    guideline_service: Annotated[ChannelGuidelineService, Depends(get_guideline_service)],
    artifact_service: Annotated[ArtifactService, Depends(get_artifact_service)],
    model_router: Annotated[ModelRouter, Depends(get_model_router)],
    agent_run_repo: Annotated[AgentRunRepository, Depends(get_agent_run_repository)],
) -> StoryboardService:
    return StoryboardService(
        app_settings=app_settings,
        project_repo=project_repo,
        script_repo=script_repo,
        scene_repo=scene_repo,
        guideline_service=guideline_service,
        artifact_service=artifact_service,
        model_router=model_router,
        agent_run_repo=agent_run_repo,
    )


def get_topic_strategist_service(
    app_settings: Annotated[Settings, Depends(get_settings)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    guideline_service: Annotated[ChannelGuidelineService, Depends(get_guideline_service)],
    artifact_service: Annotated[ArtifactService, Depends(get_artifact_service)],
    model_router: Annotated[ModelRouter, Depends(get_model_router)],
    approval_service: Annotated[ApprovalService, Depends(get_approval_service)],
    agent_run_repo: Annotated[AgentRunRepository, Depends(get_agent_run_repository)],
) -> TopicStrategistService:
    return TopicStrategistService(
        app_settings=app_settings,
        project_repo=project_repo,
        guideline_service=guideline_service,
        artifact_service=artifact_service,
        model_router=model_router,
        approval_service=approval_service,
        agent_run_repo=agent_run_repo,
    )


def get_image_provider() -> BaseImageProvider:
    return LocalSVGImageProvider()


def get_asset_generation_service(
    app_settings: Annotated[Settings, Depends(get_settings)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    scene_repo: Annotated[SceneRepository, Depends(get_scene_repository)],
    artifact_service: Annotated[ArtifactService, Depends(get_artifact_service)],
    model_router: Annotated[ModelRouter, Depends(get_model_router)],
    image_provider: Annotated[BaseImageProvider, Depends(get_image_provider)],
    agent_run_repo: Annotated[AgentRunRepository, Depends(get_agent_run_repository)],
) -> AssetGenerationService:
    return AssetGenerationService(
        app_settings=app_settings,
        project_repo=project_repo,
        scene_repo=scene_repo,
        artifact_service=artifact_service,
        model_router=model_router,
        image_provider=image_provider,
        agent_run_repo=agent_run_repo,
    )


def get_asset_qa_service(
    artifact_service: Annotated[ArtifactService, Depends(get_artifact_service)],
    approval_service: Annotated[ApprovalService, Depends(get_approval_service)],
) -> AssetQAService:
    return AssetQAService(
        artifact_service=artifact_service,
        approval_service=approval_service,
    )


def get_youtube_strategy_service(
    app_settings: Annotated[Settings, Depends(get_settings)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    script_repo: Annotated[ScriptRepository, Depends(get_script_repository)],
    scene_repo: Annotated[SceneRepository, Depends(get_scene_repository)],
    competitor_repo: Annotated[CompetitorRepository, Depends(get_competitor_repository)],
    guideline_service: Annotated[ChannelGuidelineService, Depends(get_guideline_service)],
    artifact_service: Annotated[ArtifactService, Depends(get_artifact_service)],
    model_router: Annotated[ModelRouter, Depends(get_model_router)],
    agent_run_repo: Annotated[AgentRunRepository, Depends(get_agent_run_repository)],
) -> YouTubeStrategyService:
    return YouTubeStrategyService(
        app_settings=app_settings,
        project_repo=project_repo,
        script_repo=script_repo,
        scene_repo=scene_repo,
        competitor_repo=competitor_repo,
        guideline_service=guideline_service,
        artifact_service=artifact_service,
        model_router=model_router,
        agent_run_repo=agent_run_repo,
    )


def get_production_service(
    app_settings: Annotated[Settings, Depends(get_settings)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    script_repo: Annotated[ScriptRepository, Depends(get_script_repository)],
    scene_repo: Annotated[SceneRepository, Depends(get_scene_repository)],
    artifact_service: Annotated[ArtifactService, Depends(get_artifact_service)],
    youtube_strategy_service: Annotated[
        YouTubeStrategyService, Depends(get_youtube_strategy_service)
    ],
    model_router: Annotated[ModelRouter, Depends(get_model_router)],
    approval_service: Annotated[ApprovalService, Depends(get_approval_service)],
    agent_run_repo: Annotated[AgentRunRepository, Depends(get_agent_run_repository)],
) -> ProductionService:
    return ProductionService(
        app_settings=app_settings,
        project_repo=project_repo,
        script_repo=script_repo,
        scene_repo=scene_repo,
        artifact_service=artifact_service,
        youtube_strategy_service=youtube_strategy_service,
        model_router=model_router,
        approval_service=approval_service,
        agent_run_repo=agent_run_repo,
    )


def get_evaluation_service(
    app_settings: Annotated[Settings, Depends(get_settings)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    research_repo: Annotated[ResearchRepository, Depends(get_research_repository)],
    fact_check_repo: Annotated[FactCheckRepository, Depends(get_fact_check_repository)],
    script_repo: Annotated[ScriptRepository, Depends(get_script_repository)],
    scene_repo: Annotated[SceneRepository, Depends(get_scene_repository)],
    usage_repo: Annotated[UsageRepository, Depends(get_usage_repository)],
    evaluation_repo: Annotated[EvaluationRepository, Depends(get_evaluation_repository)],
    artifact_service: Annotated[ArtifactService, Depends(get_artifact_service)],
    model_router: Annotated[ModelRouter, Depends(get_model_router)],
) -> EvaluationService:
    return EvaluationService(
        app_settings=app_settings,
        project_repo=project_repo,
        research_repo=research_repo,
        fact_check_repo=fact_check_repo,
        script_repo=script_repo,
        scene_repo=scene_repo,
        usage_repo=usage_repo,
        evaluation_repo=evaluation_repo,
        artifact_service=artifact_service,
        model_router=model_router,
    )


def get_workflow_orchestrator(
    app_settings: Annotated[Settings, Depends(get_settings)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    run_repo: Annotated[RunRepository, Depends(get_run_repository)],
    agent_run_repo: Annotated[AgentRunRepository, Depends(get_agent_run_repository)],
    topic_strategist: Annotated[TopicStrategistService, Depends(get_topic_strategist_service)],
    research_service: Annotated[ResearchService, Depends(get_research_service)],
    competitor_service: Annotated[CompetitorService, Depends(get_competitor_service)],
    fact_check_service: Annotated[FactCheckService, Depends(get_fact_check_service)],
    scriptwriter_service: Annotated[ScriptwriterService, Depends(get_scriptwriter_service)],
    storyboard_service: Annotated[StoryboardService, Depends(get_storyboard_service)],
    approval_service: Annotated[ApprovalService, Depends(get_approval_service)],
) -> WorkflowOrchestrator:
    services = PipelineServices(
        topic_strategist=topic_strategist,
        research=research_service,
        competitor=competitor_service,
        fact_checker=fact_check_service,
        scriptwriter=scriptwriter_service,
        storyboard=storyboard_service,
        approval=approval_service,
    )
    return WorkflowOrchestrator(
        app_settings=app_settings,
        project_repo=project_repo,
        run_repo=run_repo,
        services=services,
        agent_run_repo=agent_run_repo,
    )
