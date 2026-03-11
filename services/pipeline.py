from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import os
import re
import subprocess
import uuid
from urllib.parse import urlparse

from django.conf import settings
from openai import OpenAI


SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".kt",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".cs",
    ".php",
    ".rb",
    ".swift",
    ".scala",
    ".sql",
    ".html",
    ".css",
    ".scss",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".md",
    ".sh",
}

SPECIAL_FILENAMES = {
    "dockerfile",
    "makefile",
    "requirements.txt",
    "package.json",
    "pyproject.toml",
    "cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "settings.gradle",
    "readme.md",
}

IGNORED_DIRECTORIES = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "target",
    "bin",
    "obj",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
}

MAX_FILES = 80
MAX_FILE_BYTES = 300_000
MAX_FILE_CHARS = 3500
MAX_TOTAL_CHARS = 70_000


@dataclass
class PipelineResult:
    job_id: str
    repository: str
    local_path: str
    analysis_text: str
    narration_text: str
    audio_url: str
    analysis_url: str

    def to_dict(self) -> dict[str, str]:
        return {
            "job_id": self.job_id,
            "repository": self.repository,
            "local_path": self.local_path,
            "analysis_text": self.analysis_text,
            "narration_text": self.narration_text,
            "audio_url": self.audio_url,
            "analysis_url": self.analysis_url,
        }


def run_pipeline(repo_url: str) -> PipelineResult:
    owner, repo_name = parse_github_repo_url(repo_url)
    repository_slug = f"{owner}/{repo_name}"
    job_id = uuid.uuid4().hex

    workspace_root = Path(settings.BASE_DIR) / "workspace_repos"
    workspace_root.mkdir(parents=True, exist_ok=True)

    media_output_root = Path(settings.MEDIA_ROOT) / "outputs"
    media_output_root.mkdir(parents=True, exist_ok=True)

    local_repo_path = workspace_root / f"{owner}__{repo_name}__{job_id[:8]}"
    clone_public_repository(owner, repo_name, local_repo_path)

    context = build_repository_context(local_repo_path)
    analysis_text, narration_text = request_analysis_and_narration(
        repo_url=repo_url.strip(),
        repository_slug=repository_slug,
        context=context,
    )

    audio_file_path = media_output_root / f"{job_id}.mp3"
    synthesize_speech(narration_text=narration_text, output_path=audio_file_path)

    analysis_file_path = media_output_root / f"{job_id}.md"
    analysis_file_path.write_text(
        f"# Repository: {repository_slug}\n\n"
        f"{analysis_text}\n\n"
        "## Narration Script\n\n"
        f"{narration_text}\n",
        encoding="utf-8",
    )

    return PipelineResult(
        job_id=job_id,
        repository=repository_slug,
        local_path=str(local_repo_path),
        analysis_text=analysis_text,
        narration_text=narration_text,
        audio_url=f"{settings.MEDIA_URL}outputs/{audio_file_path.name}",
        analysis_url=f"{settings.MEDIA_URL}outputs/{analysis_file_path.name}",
    )


def parse_github_repo_url(repo_url: str) -> tuple[str, str]:
    cleaned = repo_url.strip()
    parsed = urlparse(cleaned)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("유효한 http/https GitHub URL을 입력해 주세요.")
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        raise ValueError("GitHub public 저장소 URL만 허용됩니다.")

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2:
        raise ValueError("GitHub 저장소 형식은 https://github.com/{owner}/{repo} 입니다.")

    owner = path_parts[0]
    repo_name = path_parts[1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    if not owner or not repo_name:
        raise ValueError("GitHub owner/repo 값을 확인해 주세요.")

    return owner, repo_name


def clone_public_repository(owner: str, repo_name: str, target_dir: Path) -> None:
    clone_url = f"https://github.com/{owner}/{repo_name}.git"
    command = ["git", "clone", "--depth", "1", clone_url, str(target_dir)]
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=240,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("저장소 클론 시간이 초과되었습니다.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise ValueError(f"저장소 클론 실패: {stderr or '알 수 없는 오류'}") from exc


def build_repository_context(repo_root: Path) -> dict[str, object]:
    candidate_paths: list[Path] = []

    for file_path in repo_root.rglob("*"):
        if not file_path.is_file():
            continue
        rel_parts = file_path.relative_to(repo_root).parts
        if any(part in IGNORED_DIRECTORIES for part in rel_parts):
            continue
        if not is_candidate_file(file_path):
            continue
        if file_path.stat().st_size > MAX_FILE_BYTES:
            continue
        candidate_paths.append(file_path)

    candidate_paths.sort(
        key=lambda path: (
            file_priority(path),
            len(path.relative_to(repo_root).parts),
            path.relative_to(repo_root).as_posix(),
        )
    )

    snippets: list[str] = []
    extension_counter: Counter[str] = Counter()
    consumed_chars = 0
    selected_count = 0

    for file_path in candidate_paths:
        if selected_count >= MAX_FILES or consumed_chars >= MAX_TOTAL_CHARS:
            break
        content = safe_read_text(file_path)
        if not content.strip():
            continue

        excerpt = content[:MAX_FILE_CHARS]
        rel_path = file_path.relative_to(repo_root).as_posix()
        extension_key = file_path.suffix.lower() or file_path.name.lower()

        extension_counter[extension_key] += 1
        consumed_chars += len(excerpt)
        selected_count += 1
        snippets.append(
            f"## {rel_path}\n"
            f"```{language_hint(file_path)}\n"
            f"{excerpt}\n"
            "```"
        )

    root_directories = sorted(
        [
            item.name
            for item in repo_root.iterdir()
            if item.is_dir() and item.name not in IGNORED_DIRECTORIES
        ]
    )

    return {
        "selected_file_count": selected_count,
        "consumed_chars": consumed_chars,
        "extension_counter": dict(sorted(extension_counter.items(), key=lambda x: x[0])),
        "root_directories": root_directories[:25],
        "snippets": "\n\n".join(snippets),
    }


def request_analysis_and_narration(
    repo_url: str,
    repository_slug: str,
    context: dict[str, object],
) -> tuple[str, str]:
    client = get_openai_client()
    analysis_model = os.getenv("OPENAI_ANALYSIS_MODEL", "gpt-4o-mini")

    system_message = (
        "당신은 시니어 소프트웨어 아키텍트입니다. "
        "입력된 저장소 코드 스냅샷을 바탕으로 기술 분석을 작성합니다. "
        "반드시 한국어로 답하고, 응답은 아래 태그 형식을 지키세요.\n"
        "[ANALYSIS]\n"
        "실행 가능한 기술 분석 본문\n"
        "[/ANALYSIS]\n"
        "[NARRATION]\n"
        "TTS용 음성 스크립트 (자연스러운 설명체, 1~2분 분량)\n"
        "[/NARRATION]"
    )

    user_message = (
        f"Repository: {repository_slug}\n"
        f"URL: {repo_url}\n"
        f"Selected files: {context['selected_file_count']}\n"
        f"Prompt chars: {context['consumed_chars']}\n"
        f"Top-level directories: {context['root_directories']}\n"
        f"Extension distribution: {context['extension_counter']}\n\n"
        "요청사항:\n"
        "1) 저장소의 핵심 목적과 문제 해결 범위를 분석\n"
        "2) 아키텍처/기술스택/주요 모듈 역할 정리\n"
        "3) 실행 흐름과 데이터 흐름 설명\n"
        "4) 리스크/기술 부채/개선 포인트 제시\n"
        "5) 마지막에는 짧은 운영 팁 제시\n\n"
        "코드 스냅샷:\n"
        f"{context['snippets']}"
    )

    response = client.chat.completions.create(
        model=analysis_model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,
    )
    raw_text = (response.choices[0].message.content or "").strip()
    analysis_text, narration_text = split_response_sections(raw_text)
    return analysis_text, narration_text


def synthesize_speech(narration_text: str, output_path: Path) -> None:
    client = get_openai_client()
    tts_model = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    tts_voice = os.getenv("OPENAI_TTS_VOICE", "alloy")

    try:
        speech_response = client.audio.speech.create(
            model=tts_model,
            voice=tts_voice,
            input=narration_text,
            response_format="mp3",
        )
    except TypeError:
        speech_response = client.audio.speech.create(
            model=tts_model,
            voice=tts_voice,
            input=narration_text,
            format="mp3",
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if hasattr(speech_response, "stream_to_file"):
        speech_response.stream_to_file(str(output_path))
        return
    if hasattr(speech_response, "write_to_file"):
        speech_response.write_to_file(str(output_path))
        return
    if hasattr(speech_response, "read"):
        output_path.write_bytes(speech_response.read())
        return

    content = getattr(speech_response, "content", None)
    if content:
        output_path.write_bytes(content)
        return

    raise RuntimeError("OpenAI 음성 응답을 파일로 저장하지 못했습니다.")


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 환경변수가 설정되어 있지 않습니다.")
    return OpenAI(api_key=api_key)


def split_response_sections(raw_text: str) -> tuple[str, str]:
    analysis_match = re.search(
        r"\[ANALYSIS\](.*?)\[/ANALYSIS\]",
        raw_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    narration_match = re.search(
        r"\[NARRATION\](.*?)\[/NARRATION\]",
        raw_text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    analysis_text = (
        analysis_match.group(1).strip()
        if analysis_match
        else raw_text.strip() or "분석 결과를 생성하지 못했습니다."
    )
    narration_text = (
        narration_match.group(1).strip()
        if narration_match
        else analysis_text[:1500]
    )

    if len(narration_text) > 3500:
        narration_text = narration_text[:3500]

    return analysis_text, narration_text


def is_candidate_file(file_path: Path) -> bool:
    suffix = file_path.suffix.lower()
    if suffix in SUPPORTED_EXTENSIONS:
        return True
    return file_path.name.lower() in SPECIAL_FILENAMES


def file_priority(file_path: Path) -> int:
    name = file_path.name.lower()
    relative_name = file_path.as_posix().lower()

    if name.startswith("readme"):
        return 0
    if name in {
        "requirements.txt",
        "pyproject.toml",
        "package.json",
        "dockerfile",
        "compose.yml",
        "docker-compose.yml",
        "go.mod",
        "cargo.toml",
        "pom.xml",
    }:
        return 1
    if "main" in name or "app" in name or "server" in name:
        return 2
    if "test" in relative_name:
        return 4
    return 3


def safe_read_text(file_path: Path) -> str:
    try:
        raw = file_path.read_bytes()
    except OSError:
        return ""
    if b"\x00" in raw:
        return ""
    return raw.decode("utf-8", errors="ignore")


def language_hint(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    return {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "jsx",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".c": "c",
        ".cpp": "cpp",
        ".cs": "csharp",
        ".php": "php",
        ".rb": "ruby",
        ".swift": "swift",
        ".scala": "scala",
        ".sql": "sql",
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".md": "markdown",
        ".sh": "bash",
    }.get(suffix, "")
