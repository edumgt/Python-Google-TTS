import os
import re
import time
import openai
from google.cloud import texttospeech
from openai import OpenAI


# === Google TTS 설정 ===
SERVICE_ACCOUNT_FILE = "my-project.json"
client = texttospeech.TextToSpeechClient.from_service_account_file(SERVICE_ACCOUNT_FILE)
voice_names = ["ko-KR-Wavenet-A", "ko-KR-Wavenet-B", "ko-KR-Wavenet-C", "ko-KR-Wavenet-D"]

# === 경로 설정 ===
base_directory = r"C:\\edumgt-test\\open-ai-batch\\Exercises"
output_folder = "output_exercise_lectures"


def find_java_groups(base_dir):
    java_dirs = {}
    for root, _, files in os.walk(base_dir):
        java_files = [f for f in files if f.endswith(".java") and f != "Main.java"]
        if java_files:
            java_dirs[root] = [os.path.join(root, f) for f in java_files]
    return java_dirs


def analyze_java_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            code = f.read()
        return code
    except Exception as e:
        return ""

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY"))

def summarize_with_openai(code: str) -> str:
    try:
        prompt = (
            "다음 Java 코드가 어떤 역할을 하는지, 주요 기능과 흐름을 한국어로 요약해줘.\n\n"
            f"{code}"
        )

        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "당신은 Java 코드를 분석하는 전문가입니다. 설명은 한국어로 해주세요."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=700
        )

        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[OpenAI 요약 실패: {e}]"


def generate_detailed_explanation(java_code: str, base_summary: str, filename: str):
    result = {}

    class_defs = re.findall(r'(public\s+)?(abstract\s+)?class\s+(\w+)', java_code)
    result['클래스 목록'] = [c[2] for c in class_defs] if class_defs else ["없음"]

    method_defs = re.findall(r'(public|private|protected)\s+[\w<>\[\]]+\s+(\w+)\s*\(.*?\)', java_code)
    result['메서드 목록'] = list(set([name for _, name in method_defs])) if method_defs else ["없음"]

    field_defs = re.findall(r'(private|public|protected)\s+[\w<>\[\]]+\s+(\w+);', java_code)
    result['프로퍼티 목록'] = list(set([name for _, name in field_defs])) if field_defs else ["없음"]

    if "new " in java_code:
        result['스택/힙 메모리 사용'] = (
            "new 키워드를 사용한 객체는 힙에 저장되며, 참조 변수는 스택에 위치합니다."
        )
    else:
        result['스택/힙 메모리 사용'] = (
            "객체 생성을 명시적으로 하지 않고, 대부분 지역 변수 중심으로 스택 메모리만 사용됩니다."
        )

    if any(ann in java_code for ann in ["@Service", "@Component", "@Controller", "@Repository", "@Autowired"]):
        result['Spring 연계'] = (
            "Spring 어노테이션이 포함되어 있어 DI 또는 컴포넌트 스캔에 사용될 수 있습니다."
        )
    else:
        result['Spring 연계'] = "POJO 기반으로 Spring 환경에 쉽게 통합 가능합니다."

    result['학습 목표'] = (
        f"클래스 구조({', '.join(result['클래스 목록'])}), "
        f"{len(result['메서드 목록'])}개 메서드, {len(result['프로퍼티 목록'])}개 속성을 통해 "
        "객체지향 개념을 학습합니다."
    )

    result['실행 결과 예측'] = (
        "main()이 존재하여 직접 실행 가능한 구조입니다." if "public static void main" in java_code
        else "main()이 없어 다른 클래스에서 호출하거나 테스트해야 합니다."
    )

    advanced_keywords = {
        "synchronized": "스레드 동기화를 위한 키워드입니다.",
        "Thread": "Java의 기본 스레드 클래스입니다.",
        "Runnable": "스레드 실행 로직을 담는 인터페이스입니다.",
        "Stream": "컬렉션 데이터를 함수형으로 처리할 수 있는 기능입니다.",
        "Lambda": "간결한 함수 표현을 위한 Java 8의 기능입니다.",
    }

    used_terms = [f"{k}: {v}" for k, v in advanced_keywords.items() if k in java_code]
    if used_terms:
        result['중급 키워드 설명'] = "\n".join(used_terms)

    business_lines = [
        line.strip() for line in java_code.splitlines()
        if any(kw in line for kw in ["if", "for", "while", "switch"])
    ]
    if business_lines:
        result['비즈니스 로직 흐름 요약'] = "\n".join(business_lines[:10])

    explanation = [f"분석 대상 디렉토리: {filename}", "", base_summary, ""]
    for section, content in result.items():
        explanation.append(f"{section} 설명:\n{content if isinstance(content, str) else ', '.join(content)}\n")

    return "\n".join(explanation)


def create_tts_mp3(text, mp3_path):
    voice = texttospeech.VoiceSelectionParams(
        language_code="ko-KR",
        name=voice_names[0],
        ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
    )
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3, speaking_rate=1.1)
    synthesis_input = texttospeech.SynthesisInput(text=text)
    response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)

    with open(mp3_path, "wb") as out:
        out.write(response.audio_content)


def generate_group_lesson(java_file_paths, group_path):
    all_code = ""
    for path in java_file_paths:
        all_code += analyze_java_file(path) + "\n"

    ai_summary = summarize_with_openai(all_code)
    filename = os.path.basename(group_path)
    save_dir = os.path.join(output_folder, os.path.relpath(group_path, base_directory))
    os.makedirs(save_dir, exist_ok=True)

    explanation = generate_detailed_explanation(all_code, ai_summary, filename)

    txt_path = os.path.join(save_dir, filename + ".txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(explanation)

    mp3_path = os.path.join(save_dir, filename + ".mp3")
    create_tts_mp3(explanation, mp3_path)

    print(f"✅ 완료: {filename} → 요약 및 TTS 생성됨")


def run_analysis_loop():
    java_groups = find_java_groups(base_directory)
    for dir_path, java_files in java_groups.items():
        generate_group_lesson(java_files, dir_path)
        time.sleep(60)


if __name__ == "__main__":
    run_analysis_loop()
