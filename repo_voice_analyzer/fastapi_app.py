from __future__ import annotations

import os

from django.core.asgi import get_asgi_application
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from services.pipeline import run_pipeline


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "repo_voice_analyzer.settings")

django_asgi_app = get_asgi_application()

app = FastAPI(
    title="Repo Voice Analyzer API",
    description="GitHub public repository analysis + OpenAI narration + TTS",
    version="1.0.0",
)


class AnalyzeRequest(BaseModel):
    repo_url: str = Field(
        ...,
        description="Public GitHub repository URL",
        examples=["https://github.com/openai/openai-python"],
    )


class AnalyzeResponse(BaseModel):
    job_id: str
    repository: str
    local_path: str
    analysis_text: str
    narration_text: str
    audio_url: str
    analysis_url: str


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_repository(payload: AnalyzeRequest) -> AnalyzeResponse:
    try:
        result = await run_in_threadpool(run_pipeline, payload.repo_url)
        return AnalyzeResponse(**result.to_dict())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"알 수 없는 오류: {exc}") from exc


app.mount("/", django_asgi_app)
