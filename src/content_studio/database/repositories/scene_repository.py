from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.database.models.enums import SceneVisualType
from content_studio.database.models.scene import Scene


class SceneRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_project(
        self,
        project_id: str,
        *,
        script_version_id: str | None,
        run_id: str | None,
        scenes_data: list[dict[str, Any]],
    ) -> list[Scene]:
        await self._session.execute(delete(Scene).where(Scene.project_id == project_id))

        created: list[Scene] = []
        for item in scenes_data:
            visual_type = item.get("visual_type", SceneVisualType.FACE_CAM.value)
            if isinstance(visual_type, SceneVisualType):
                visual_type = visual_type.value
            scene = Scene(
                project_id=project_id,
                script_version_id=script_version_id,
                run_id=run_id,
                scene_number=int(item["scene_number"]),
                title=str(item["title"])[:300],
                estimated_duration_seconds=int(item.get("estimated_duration_seconds", 45)),
                narration=str(item["narration"]),
                on_screen_text=item.get("on_screen_text"),
                visual_type=str(visual_type),
                asset_requirements_json=list(item.get("asset_requirements", [])),
                camera_or_screen_instructions=item.get("camera_or_screen_instructions"),
                transition_instructions=item.get("transition_instructions"),
                related_script_section=str(item.get("related_script_section") or "")[:100],
            )
            self._session.add(scene)
            created.append(scene)

        await self._session.commit()
        for scene in created:
            await self._session.refresh(scene)
        return created

    async def list_for_project(self, project_id: str) -> Sequence[Scene]:
        stmt = (
            select(Scene).where(Scene.project_id == project_id).order_by(Scene.scene_number.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
