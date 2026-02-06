# Python Gen Java Edu

Java 소스 코드를 자동 분석하고, 설명 텍스트/음성/영상까지 생성하는 **교육용 콘텐츠 자동화 프로젝트**입니다.

## 1) 프로젝트 개요
- Java 예제 파일을 스캔하고 코드 구조를 분석합니다.
- OpenAI 모델로 Java 코드 요약/설명을 생성합니다.
- Google Cloud Text-to-Speech로 한국어 음성을 생성합니다.
- ffmpeg/Pillow를 사용해 텍스트 오버레이 영상이나 슬라이드형 영상을 합성합니다.
- 일부 스크립트는 Diffusers + PyTorch 기반 Text-to-Video 실험 기능을 포함합니다.

---

## 2) 기술 스택 (상세)

### 언어/런타임
- **Python 3.x**

### AI/LLM
- **OpenAI Python SDK (`openai`)**
  - Java 코드 분석 요약
  - 설명 문장 생성
  - 교육용 스크립트 생성

### 음성(TTS)
- **Google Cloud Text-to-Speech (`google-cloud-texttospeech`)**
  - 한국어 WaveNet 음성 생성
- **gTTS (`gtts`)**
  - 간단한 텍스트 음성 변환

### 영상/오디오 처리
- **ffmpeg-python (`ffmpeg`)**
  - 배경 영상 생성
  - 텍스트 오버레이
  - 오디오/비디오 mux
  - 필터(리버브 등) 적용
- **pydub**
  - WAV → MP3 변환
- **mutagen**
  - MP3 길이 메타데이터 조회
- **scipy / numpy**
  - 오디오 파형 합성 및 저장

### 이미지 처리
- **Pillow (`PIL`)**
  - 자막/텍스트 이미지 생성

### 비디오 생성(실험)
- **PyTorch (`torch`)**
- **Diffusers (`diffusers`)**
- **imageio**
- **OpenCV (`cv2`)**
  - 텍스트 기반 비디오 생성/프레임 후처리 실험 스크립트

### 데이터/설정
- **JSON 설정 파일**
  - OAuth/Service Account 관련 설정

---

## 3) 주요 스크립트 역할
- `work.py`, `batch.py`, `batch2.py`, `singledirwork.py`
  - Java 파일 단위/디렉토리 단위 분석
  - OpenAI 요약 + Google TTS + 영상 합성 파이프라인
- `VoiceToMp3Kr.py`
  - 한국어 TTS 중심 처리
- `OpenAI.py`, `OpenAI2.py`
  - GPT 기반 스토리/사운드 생성 및 ffmpeg 후처리
- `OpenAI3.py` ~ `OpenAI7.py`
  - Diffusers/PyTorch 기반 영상 생성 실험

---

## 4) 민감정보(Secret) 마스킹 정책
이 저장소는 보안 강화를 위해 **실제 키/토큰/계정정보를 직접 커밋하지 않도록** 정리되었습니다.

- OpenAI API Key: 코드 내 하드코딩 대신 `OPENAI_API_KEY` 환경변수 사용
- Google OAuth/Service Account JSON: 실제 값 대신 `***MASKED_...***` 플레이스홀더 사용

### 필수 환경변수
```bash
export OPENAI_API_KEY="your-real-openai-key"
```

### 권장 보안 수칙
1. `.env` 또는 Secret Manager 사용
2. `client_secret.json`, `my-project.json` 실제 파일은 Git 추적 제외(`.gitignore`) 처리
3. 키가 노출되었을 경우 즉시 폐기(rotate) 후 재발급
4. CI/CD에는 리포지토리 비밀변수로 주입

---

## 5) 실행 전 준비
1. Python 가상환경 생성
2. 의존성 설치
   ```bash
   pip install openai google-cloud-texttospeech gtts ffmpeg-python pillow mutagen pydub scipy numpy torch diffusers imageio opencv-python
   ```
3. 시스템에 ffmpeg 설치
4. Google Cloud 인증 파일(실제 값) 준비 후 로컬 경로로 연결

---

## 6) 현재 구조의 특징
- 장점
  - 코드 분석 → 설명 생성 → 음성/영상 산출까지 자동화 범위가 넓음
  - 교육 콘텐츠 생성 파이프라인 실험에 적합
- 개선 포인트
  - 스크립트별 중복 로직(요약/TTS/합성)을 모듈화하면 유지보수성 향상
  - 의존성 잠금(`requirements.txt`) 및 실행 엔트리포인트 통일 필요
  - 설정 파일 경로/출력 경로를 CLI 인자로 일반화하면 재사용성 상승

---

## 7) 라이선스/주의
- 외부 API(OpenAI/Google Cloud) 사용 시 과금이 발생할 수 있습니다.
- 생성형 AI 결과물은 교육용 검수 과정을 거쳐 활용하는 것을 권장합니다.
