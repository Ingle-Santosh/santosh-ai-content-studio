from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    env: str
    local_only: bool
    data_dir: str
    ollama_base_url: str
    default_model: str
