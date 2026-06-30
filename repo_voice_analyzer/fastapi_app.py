from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings
from django.core.asgi import get_asgi_application
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from services.pipeline import PROVIDERS, resolve_provider, run_pipeline


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "repo_voice_analyzer.settings")

django_asgi_app = get_asgi_application()
Path(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Financial Site Voice Analyzer API",
    description="국내외 금융/투자 사이트 콘텐츠 분석 + AI 인사이트 + TTS 음성 생성",
    version="2.0.0",
)


class AnalyzeRequest(BaseModel):
    site_url: str = Field(
        ...,
        description="분석할 금융/투자 사이트 URL",
        examples=["https://finance.naver.com", "https://finance.yahoo.com"],
    )
    provider: str = Field(
        default="auto",
        description="사용할 AI 모델 (auto, openai, ollama, solar)",
    )


class AnalyzeResponse(BaseModel):
    job_id: str
    site_url: str
    site_name: str
    crawled_text: str
    analysis_text: str
    narration_text: str
    audio_url: str
    analysis_url: str
    provider: str


class ProviderInfo(BaseModel):
    id: str
    label: str
    available: bool


class ProvidersResponse(BaseModel):
    providers: list[ProviderInfo]
    default: str


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/providers", response_model=ProvidersResponse)
def list_providers() -> ProvidersResponse:
    labels = {
        "openai": "OpenAI (GPT-4o-mini)",
        "ollama": "Ollama (로컬 PC)",
        "solar": "Upstage Solar",
    }
    availability = {
        "openai": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "ollama": True,
        "solar": bool(os.getenv("UPSTAGE_API_KEY", "").strip()),
    }
    return ProvidersResponse(
        providers=[
            ProviderInfo(id=p, label=labels[p], available=availability[p])
            for p in PROVIDERS
        ],
        default=resolve_provider(None),
    )


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_financial_site(payload: AnalyzeRequest) -> AnalyzeResponse:
    try:
        result = await run_in_threadpool(run_pipeline, payload.site_url, payload.provider)
        return AnalyzeResponse(**result.to_dict())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"알 수 없는 오류: {exc}") from exc


app.mount(settings.MEDIA_URL, StaticFiles(directory=settings.MEDIA_ROOT), name="media")
app.mount("/", django_asgi_app)
