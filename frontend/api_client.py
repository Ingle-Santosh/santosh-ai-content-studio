from typing import Any

import httpx


class StudioAPIError(RuntimeError):
    """Raised when the FastAPI backend returns an error or is unreachable."""


class StudioAPIClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        try:
            response = httpx.request(
                method,
                url,
                json=json,
                params=params,
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            raise StudioAPIError(
                f"Backend returned HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise StudioAPIError(f"Failed to reach backend at {self._base_url}: {exc}") from exc

        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def get_health(self) -> dict[str, Any]:
        return dict(self._request("GET", "/health"))

    def list_projects(self, *, limit: int = 50) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/projects", params={"limit": limit})
        return list(payload.get("items", []))

    def create_project(
        self,
        *,
        topic: str,
        title: str | None = None,
        duration_minutes: int = 15,
        language: str = "Hinglish",
        audience_level: str = "Intermediate (Data/AI Engineers)",
        include_code_demo: bool = True,
        include_animations: bool = True,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "topic": topic,
            "title": title or None,
            "config": {
                "duration_minutes": duration_minutes,
                "language": language,
                "audience_level": audience_level,
                "include_code_demo": include_code_demo,
                "include_animations": include_animations,
            },
        }
        return dict(self._request("POST", "/api/projects", json=body))

    def delete_project(self, project_id: str) -> None:
        self._request("DELETE", f"/api/projects/{project_id}")

    # Artifacts
    def list_artifacts(
        self,
        project_id: str,
        *,
        stage: str | None = None,
        artifact_type: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if stage:
            params["stage"] = stage
        if artifact_type:
            params["artifact_type"] = artifact_type
        payload = self._request(
            "GET", f"/api/projects/{project_id}/artifacts", params=params or None
        )
        return list(payload.get("items", []))

    def create_artifact(
        self,
        project_id: str,
        *,
        stage: str,
        artifact_type: str,
        name: str,
        content: str,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "stage": stage,
            "artifact_type": artifact_type,
            "name": name,
            "content": content,
            "metadata_json": metadata_json or {},
        }
        return dict(self._request("POST", f"/api/projects/{project_id}/artifacts", json=body))

    def get_artifact_content(self, project_id: str, artifact_id: str) -> dict[str, Any]:
        return dict(
            self._request("GET", f"/api/projects/{project_id}/artifacts/{artifact_id}/content")
        )

    def verify_artifact(self, project_id: str, artifact_id: str) -> dict[str, Any]:
        return dict(
            self._request("GET", f"/api/projects/{project_id}/artifacts/{artifact_id}/verify")
        )

    # Channel Guidelines
    def get_active_guideline(self) -> dict[str, Any]:
        return dict(self._request("GET", "/api/guidelines/active"))

    def upsert_guideline(
        self,
        slug: str,
        *,
        channel_name: str,
        guidelines: dict[str, Any],
        is_active: bool = True,
    ) -> dict[str, Any]:
        body = {
            "channel_name": channel_name,
            "is_active": is_active,
            "guidelines": guidelines,
        }
        return dict(self._request("PUT", f"/api/guidelines/{slug}", json=body))

    # Approvals
    def list_approvals(
        self,
        *,
        project_id: str | None = None,
        status: str | None = None,
        gate: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if project_id:
            params["project_id"] = project_id
        if status:
            params["status"] = status
        if gate:
            params["gate"] = gate
        payload = self._request("GET", "/api/approvals", params=params or None)
        return list(payload.get("items", []))

    def decide_approval(
        self,
        approval_id: str,
        *,
        status: str,
        reviewer: str | None = None,
        comments: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "status": status,
            "reviewer": reviewer,
            "comments": comments,
        }
        return dict(self._request("PATCH", f"/api/approvals/{approval_id}", json=body))

    # LLM Status & Usage
    def get_llm_status(self) -> dict[str, Any]:
        return dict(self._request("GET", "/api/llm/status"))

    def get_project_usage(self, project_id: str) -> dict[str, Any]:
        return dict(self._request("GET", f"/api/projects/{project_id}/usage"))

    # Research Engine
    def run_research(
        self,
        project_id: str,
        *,
        queries: list[str] | None = None,
        seed_urls: list[str] | None = None,
        max_results_per_query: int = 5,
        synthesize_with_llm: bool = True,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "queries": queries,
            "seed_urls": seed_urls,
            "max_results_per_query": max_results_per_query,
            "synthesize_with_llm": synthesize_with_llm,
        }
        return dict(self._request("POST", f"/api/projects/{project_id}/research/run", json=body))

    def list_research_sources(
        self,
        project_id: str,
        *,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        params = {"status": status} if status else None
        payload = self._request(
            "GET", f"/api/projects/{project_id}/research/sources", params=params
        )
        return list(payload.get("items", []))

    def list_research_findings(self, project_id: str) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/api/projects/{project_id}/research/findings")
        return list(payload.get("items", []))

    # Fact Checking & Competitor Analysis
    def run_fact_check(
        self,
        project_id: str,
        *,
        custom_claims: list[str] | None = None,
        request_research_approval: bool = True,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "custom_claims": custom_claims,
            "request_research_approval": request_research_approval,
        }
        return dict(self._request("POST", f"/api/projects/{project_id}/fact-check/run", json=body))

    def list_claims(
        self,
        project_id: str,
        *,
        verdict: str | None = None,
    ) -> list[dict[str, Any]]:
        params = {"verdict": verdict} if verdict else None
        payload = self._request(
            "GET", f"/api/projects/{project_id}/fact-check/claims", params=params
        )
        return list(payload.get("items", []))

    def run_competitor_analysis(
        self,
        project_id: str,
        *,
        queries: list[str] | None = None,
        video_urls: list[str] | None = None,
        max_results: int = 5,
        analyze_with_llm: bool = True,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "queries": queries,
            "video_urls": video_urls,
            "max_results": max_results,
            "analyze_with_llm": analyze_with_llm,
        }
        return dict(self._request("POST", f"/api/projects/{project_id}/competitors/run", json=body))

    def list_competitors(self, project_id: str) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/api/projects/{project_id}/competitors")
        return list(payload.get("items", []))

    # Scriptwriting & Storyboarding
    def generate_script(
        self,
        project_id: str,
        *,
        revision_notes: str | None = None,
        require_approved_research: bool = False,
        request_script_approval: bool = True,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "revision_notes": revision_notes,
            "require_approved_research": require_approved_research,
            "request_script_approval": request_script_approval,
        }
        return dict(
            self._request("POST", f"/api/projects/{project_id}/scripts/generate", json=body)
        )

    def get_script(self, project_id: str) -> dict[str, Any] | None:
        try:
            return dict(self._request("GET", f"/api/projects/{project_id}/scripts"))
        except StudioAPIError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise

    def approve_script_version(
        self,
        project_id: str,
        version_number: int,
        *,
        reviewer: str = "Creator",
        comments: str | None = None,
    ) -> dict[str, Any]:
        body = {"reviewer": reviewer, "comments": comments}
        return dict(
            self._request(
                "POST",
                f"/api/projects/{project_id}/scripts/versions/{version_number}/approve",
                json=body,
            )
        )

    def generate_storyboard(
        self,
        project_id: str,
        *,
        script_version_number: int | None = None,
        require_approved_script: bool = True,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "script_version_number": script_version_number,
            "require_approved_script": require_approved_script,
        }
        return dict(
            self._request("POST", f"/api/projects/{project_id}/storyboard/generate", json=body)
        )

    def list_scenes(self, project_id: str) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/api/projects/{project_id}/storyboard/scenes")
        return list(payload.get("items", []))

    # LangGraph Workflows
    def start_workflow(
        self,
        project_id: str,
        *,
        seed_urls: list[str] | None = None,
        max_results_per_query: int = 5,
        auto_approve: bool | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "seed_urls": seed_urls,
            "max_results_per_query": max_results_per_query,
            "auto_approve": auto_approve,
        }
        return dict(self._request("POST", f"/api/projects/{project_id}/workflows/start", json=body))

    def list_project_workflows(self, project_id: str) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/api/projects/{project_id}/workflows")
        return list(payload.get("items", []))

    def get_workflow_status(self, run_id: str) -> dict[str, Any]:
        return dict(self._request("GET", f"/api/workflows/{run_id}"))

    def resume_workflow(
        self,
        run_id: str,
        *,
        decision: str,
        reviewer: str = "Creator",
        comments: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "decision": decision,
            "reviewer": reviewer,
            "comments": comments,
        }
        return dict(self._request("POST", f"/api/workflows/{run_id}/resume", json=body))

    def cancel_workflow(self, run_id: str) -> dict[str, Any]:
        return dict(self._request("POST", f"/api/workflows/{run_id}/cancel"))

    # Visual & Code Assets
    def plan_assets(self, project_id: str) -> dict[str, Any]:
        return dict(self._request("POST", f"/api/projects/{project_id}/assets/plan"))

    def generate_assets(
        self,
        project_id: str,
        *,
        asset_keys: list[str] | None = None,
        run_qa: bool = True,
        request_assets_approval: bool = True,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "asset_keys": asset_keys,
            "run_qa": run_qa,
            "request_assets_approval": request_assets_approval,
        }
        return dict(self._request("POST", f"/api/projects/{project_id}/assets/generate", json=body))

    def run_asset_qa(
        self,
        project_id: str,
        *,
        request_assets_approval: bool = True,
    ) -> dict[str, Any]:
        body = {"request_assets_approval": request_assets_approval}
        return dict(self._request("POST", f"/api/projects/{project_id}/assets/qa", json=body))

    def upload_screenshot(
        self,
        project_id: str,
        *,
        filename: str,
        content_base64: str,
        captured_by: str,
        source_url: str | None = None,
        scene_number: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "filename": filename,
            "content_base64": content_base64,
            "provenance": {
                "source_origin": "user_upload",
                "captured_by": captured_by,
                "source_url": source_url or None,
            },
            "scene_number": scene_number,
        }
        return dict(
            self._request("POST", f"/api/projects/{project_id}/assets/screenshots", json=body)
        )
