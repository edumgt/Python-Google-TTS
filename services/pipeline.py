from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from openai import OpenAI


MAX_CONTENT_CHARS = 12_000

_SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_REMOVE_TAGS = {
    "script", "style", "noscript", "iframe", "nav", "footer",
    "header", "aside", "form", "button", "svg", "img", "video",
    "audio", "ads", "advertisement",
}

ALLOWED_FINANCIAL_DOMAINS = {
    # 국내
    "finance.naver.com",
    "m.stock.naver.com",
    "finance.daum.net",
    "www.krx.co.kr",
    "krx.co.kr",
    "www.hankyung.com",
    "hankyung.com",
    "www.mk.co.kr",
    "mk.co.kr",
    "www.sedaily.com",
    "sedaily.com",
    "www.etnews.com",
    "fnguide.com",
    "www.fnguide.com",
    "stockplus.com",
    "www.stockplus.com",
    "investing.co.kr",
    "www.investing.co.kr",
    "infostock.co.kr",
    "www.infostock.co.kr",
    "thebell.co.kr",
    "www.thebell.co.kr",
    # 국외
    "finance.yahoo.com",
    "www.bloomberg.com",
    "bloomberg.com",
    "www.reuters.com",
    "reuters.com",
    "www.investing.com",
    "investing.com",
    "www.marketwatch.com",
    "marketwatch.com",
    "www.seekingalpha.com",
    "seekingalpha.com",
    "www.tradingview.com",
    "tradingview.com",
    "www.wsj.com",
    "wsj.com",
    "www.ft.com",
    "ft.com",
    "www.cnbc.com",
    "cnbc.com",
    "www.fool.com",
    "fool.com",
    "finviz.com",
    "www.finviz.com",
}


@dataclass
class PipelineResult:
    job_id: str
    site_url: str
    site_name: str
    analysis_text: str
    narration_text: str
    audio_url: str
    analysis_url: str

    def to_dict(self) -> dict[str, str]:
        return {
            "job_id": self.job_id,
            "site_url": self.site_url,
            "site_name": self.site_name,
            "analysis_text": self.analysis_text,
            "narration_text": self.narration_text,
            "audio_url": self.audio_url,
            "analysis_url": self.analysis_url,
        }


def run_pipeline(site_url: str) -> PipelineResult:
    validated_url = validate_financial_url(site_url)
    job_id = uuid.uuid4().hex

    media_output_root = Path(settings.MEDIA_ROOT) / "outputs"
    media_output_root.mkdir(parents=True, exist_ok=True)

    page_content = fetch_website_content(validated_url)
    site_name = page_content["title"] or urlparse(validated_url).netloc

    analysis_text, narration_text = request_analysis_and_narration(
        site_url=validated_url,
        site_name=site_name,
        page_content=page_content,
    )

    audio_file_path = media_output_root / f"{job_id}.mp3"
    synthesize_speech(narration_text=narration_text, output_path=audio_file_path)

    analysis_file_path = media_output_root / f"{job_id}.md"
    analysis_file_path.write_text(
        f"# 금융 사이트 분석: {site_name}\n\n"
        f"URL: {validated_url}\n\n"
        f"{analysis_text}\n\n"
        "## 음성 스크립트\n\n"
        f"{narration_text}\n",
        encoding="utf-8",
    )

    return PipelineResult(
        job_id=job_id,
        site_url=validated_url,
        site_name=site_name,
        analysis_text=analysis_text,
        narration_text=narration_text,
        audio_url=f"{settings.MEDIA_URL}outputs/{audio_file_path.name}",
        analysis_url=f"{settings.MEDIA_URL}outputs/{analysis_file_path.name}",
    )


def validate_financial_url(url: str) -> str:
    cleaned = url.strip()
    parsed = urlparse(cleaned)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("유효한 http/https URL을 입력해 주세요.")

    netloc = parsed.netloc.lower().lstrip("www.")
    full_netloc = parsed.netloc.lower()
    if full_netloc not in ALLOWED_FINANCIAL_DOMAINS and netloc not in ALLOWED_FINANCIAL_DOMAINS:
        allowed_list = ", ".join(sorted(ALLOWED_FINANCIAL_DOMAINS)[:10])
        raise ValueError(
            f"지원하지 않는 도메인입니다. 지원 사이트 예시: {allowed_list} 등"
        )

    return cleaned


def fetch_website_content(url: str) -> dict[str, object]:
    try:
        response = requests.get(
            url,
            headers=_SCRAPE_HEADERS,
            timeout=20,
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout as exc:
        raise RuntimeError("사이트 응답 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.") from exc
    except requests.exceptions.RequestException as exc:
        raise ValueError(f"사이트 접근 실패: {exc}") from exc

    # 인코딩 감지
    if response.encoding and response.encoding.lower() in {"utf-8", "utf8"}:
        html = response.text
    else:
        detected = response.apparent_encoding or "utf-8"
        html = response.content.decode(detected, errors="ignore")

    soup = BeautifulSoup(html, "lxml")

    # 불필요한 태그 제거
    for tag in soup.find_all(_REMOVE_TAGS):
        tag.decompose()

    # 페이지 제목
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # 메타 설명
    meta_desc = ""
    meta_tag = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
    if meta_tag and meta_tag.get("content"):
        meta_desc = meta_tag["content"].strip()

    # 본문 우선순위: <article> > <main> > <div class=content…> > <body>
    body_el = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", class_=re.compile(r"(content|article|news|stock|market)", re.I))
        or soup.body
    )

    raw_text = (body_el or soup).get_text(separator="\n", strip=True)
    # 빈 줄 정리
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    body_text = "\n".join(lines)

    # 테이블 데이터 수집 (시세 등)
    table_snippets: list[str] = []
    for table in (body_el or soup).find_all("table")[:5]:
        rows = []
        for tr in table.find_all("tr")[:15]:
            cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            table_snippets.append("\n".join(rows))

    table_text = "\n\n".join(table_snippets)

    # 전체 컨텍스트 조합 후 길이 제한
    combined = f"[제목]\n{title}\n\n[요약]\n{meta_desc}\n\n[본문]\n{body_text}"
    if table_text:
        combined += f"\n\n[시세/데이터 테이블]\n{table_text}"

    if len(combined) > MAX_CONTENT_CHARS:
        combined = combined[:MAX_CONTENT_CHARS] + "\n\n...(내용 일부 생략)"

    return {
        "title": title,
        "meta_desc": meta_desc,
        "body_preview": body_text[:200],
        "combined_text": combined,
        "char_count": len(combined),
    }


def request_analysis_and_narration(
    site_url: str,
    site_name: str,
    page_content: dict[str, object],
) -> tuple[str, str]:
    client = get_openai_client()
    analysis_model = os.getenv("OPENAI_ANALYSIS_MODEL", "gpt-4o-mini")

    system_message = (
        "당신은 국내외 금융시장과 주식 투자 전문가입니다. "
        "입력된 금융/투자 사이트의 콘텐츠를 바탕으로 시장 분석과 투자 인사이트를 작성합니다. "
        "반드시 한국어로 답하고, 응답은 아래 태그 형식을 지키세요.\n\n"
        "[ANALYSIS]\n"
        "상세 시장 분석 본문 (마크다운 형식)\n"
        "[/ANALYSIS]\n"
        "[NARRATION]\n"
        "TTS용 음성 스크립트 (자연스러운 설명체, 1~2분 분량, 마크다운 기호 없이 순수 텍스트)\n"
        "[/NARRATION]"
    )

    user_message = (
        f"분석 대상 사이트: {site_name}\n"
        f"URL: {site_url}\n"
        f"수집 콘텐츠 글자 수: {page_content['char_count']}\n\n"
        "요청사항:\n"
        "1) 현재 시장 상황 및 주요 이슈 요약 (국내/해외 구분)\n"
        "2) 주요 종목·지수·자산 동향 분석 (등락률, 거래량, 특이사항)\n"
        "3) 핵심 투자 시사점 및 주목할 섹터/테마\n"
        "4) 단기·중기 투자 아이디어 및 주의 리스크\n"
        "5) 개인 투자자를 위한 실전 조언 1~2가지\n\n"
        "※ 특정 종목 매수·매도 추천은 지양하고, 시장 흐름과 참고 정보 중심으로 서술하세요.\n\n"
        f"--- 수집된 콘텐츠 ---\n{page_content['combined_text']}"
    )

    response = client.chat.completions.create(
        model=analysis_model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
    )
    raw_text = (response.choices[0].message.content or "").strip()
    return split_response_sections(raw_text)


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
