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
