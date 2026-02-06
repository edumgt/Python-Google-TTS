import os
import re
import time
import textwrap
from PIL import Image, ImageDraw, ImageFont
from google.cloud import texttospeech
from openai import OpenAI
from mutagen.mp3 import MP3
import ffmpeg

# === 설정 ===
SERVICE_ACCOUNT_FILE = "my-project.json"
client = texttospeech.TextToSpeechClient.from_service_account_file(SERVICE_ACCOUNT_FILE)
voice_names = ["ko-KR-Wavenet-A", "ko-KR-Wavenet-B", "ko-KR-Wavenet-C", "ko-KR-Wavenet-D"]

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY"))  # ← 수정 필요
base_directory = r"C:\\devops\\python-gen-java-edu\\Exercises"
output_folder = "output_exercise_lectures"

# === Java 코드 분석 ===
def analyze_java_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return ""

def summarize_with_openai(code: str) -> str:
    try:
        prompt = f"다음 Java 코드가 어떤 역할을 하는지, 주요 기능과 흐름을 한국어로 요약해줘.\n\n{code}"
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

def generate_detailed_explanation(java_code, base_summary, filename):
    result = {}
    result['클래스 목록'] = [m[2] for m in re.findall(r'(public\s+)?(abstract\s+)?class\s+(\w+)', java_code)] or ["없음"]
    result['메서드 목록'] = list(set(m[1] for m in re.findall(r'(public|private|protected)\s+[\w<>\[\]]+\s+(\w+)\s*\(.*?\)', java_code))) or ["없음"]
    result['프로퍼티 목록'] = list(set(m[1] for m in re.findall(r'(private|public|protected)\s+[\w<>\[\]]+\s+(\w+);', java_code))) or ["없음"]
    result['스택/힙 메모리 사용'] = "new 키워드를 사용한 객체는 힙에 저장되며, 참조 변수는 스택에 위치합니다." if "new " in java_code else "객체 생성을 명시적으로 하지 않음"
    result['Spring 연계'] = "Spring 어노테이션 포함됨" if any(tag in java_code for tag in ["@Service", "@Component", "@Autowired"]) else "Spring 연계 없음"
    result['학습 목표'] = f"클래스({', '.join(result['클래스 목록'])}), 메서드 {len(result['메서드 목록'])}개, 속성 {len(result['프로퍼티 목록'])}개로 객체지향 학습"
    result['실행 결과 예측'] = "main() 메서드 존재" if "public static void main" in java_code else "main() 없음"
    keywords = {
        "synchronized": "스레드 동기화 키워드",
        "Thread": "Java 스레드 클래스",
        "Runnable": "실행 가능한 인터페이스",
        "Stream": "함수형 데이터 처리",
        "Lambda": "람다 표현식 (Java 8)"
    }
    used_terms = [f"{k}: {v}" for k, v in keywords.items() if k in java_code]
    if used_terms:
        result['중급 키워드 설명'] = "\n".join(used_terms)
    logic_lines = [line.strip() for line in java_code.splitlines() if any(kw in line for kw in ["if", "for", "while", "switch"])]
    if logic_lines:
        result['비즈니스 로직 흐름 요약'] = "\n".join(logic_lines[:3])

    explanation = [f"[{filename} Java 파일 설명]", "", base_summary, ""]
    for key, val in result.items():
        explanation.append(f"{key}:\n{val if isinstance(val, str) else ', '.join(val)}\n")
    return "\n".join(explanation)

# === TTS 및 시각자료 ===
def create_tts_mp3(text, mp3_path):
    voice = texttospeech.VoiceSelectionParams(
        language_code="ko-KR",
        name=voice_names[0],
        ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
    )
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3, speaking_rate=1.1)
    synthesis_input = texttospeech.SynthesisInput(text=text)
    response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
    with open(mp3_path, "wb") as f:
        f.write(response.audio_content)

def save_text_as_image(text, image_path, width=720, height=1280, font_size=20, font_path="C:\\Windows\\Fonts\\malgunbd.ttf"):
    image = Image.new("RGB", (width, height), "black")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, font_size) if os.path.exists(font_path) else ImageFont.load_default()
    margin = 22
    line_height = font_size + 6
    y = margin
    for line in text.splitlines():
        for sub in textwrap.wrap(line, width=80):
            if y + line_height > height - margin:
                break
            draw.text((margin, y), sub, font=font, fill="white")
            y += line_height
    image.save(image_path)

def get_mp3_duration(mp3_path):
    audio = MP3(mp3_path)
    return int(audio.info.length)

def create_slideshow_with_audio(image_paths, audio_path, output_path):
    if not os.path.exists(audio_path) or not image_paths:
        print("❌ 파일 경로 오류")
        return
    duration = get_mp3_duration(audio_path)
    temp_video = output_path.replace(".mp4", "_temp.mp4")
    ffmpeg.input(image_paths[0], loop=1, t=duration).output(
        temp_video, vf="scale=720:1280", r=30, pix_fmt="yuv420p", vcodec="libx264"
    ).run(overwrite_output=True)
    ffmpeg.output(
        ffmpeg.input(temp_video), ffmpeg.input(audio_path),
        output_path, vcodec="copy", acodec="aac", shortest=None, pix_fmt="yuv420p"
    ).run(overwrite_output=True)
    os.remove(temp_video)
    print(f"🎞️ MP4 저장 완료: {output_path}")

# === 전체 파이프라인 ===
def generate_lesson_from_single_file(java_file_path):
    java_code = analyze_java_file(java_file_path)
    if not java_code.strip():
        return
    summary = summarize_with_openai(java_code)
    filename = os.path.splitext(os.path.basename(java_file_path))[0]
    os.makedirs(output_folder, exist_ok=True)

    txt_path = os.path.join(output_folder, filename + ".txt")
    mp3_path = os.path.join(output_folder, filename + ".mp3")
    png_path = os.path.join(output_folder, filename + ".png")
    mp4_path = os.path.join(output_folder, filename + ".mp4")

    explanation = generate_detailed_explanation(java_code, summary, filename)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(explanation)

    create_tts_mp3(explanation, mp3_path)
    save_text_as_image(java_code, png_path)
    create_slideshow_with_audio([png_path], mp3_path, mp4_path)

    print(f"✅ {filename} 완료 → TXT, MP3, PNG, MP4")

# === 루프 실행 ===
def run_analysis_loop():
    for root, _, files in os.walk(base_directory):
        for file in files:
            if file.endswith(".java"):
                full_path = os.path.join(root, file)
                generate_lesson_from_single_file(full_path)
                time.sleep(5)  # 간격 조절

if __name__ == "__main__":
    run_analysis_loop()
