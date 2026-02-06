from openai import OpenAI
import numpy as np
from scipy.io.wavfile import write
from pydub import AudioSegment
import ffmpeg
import os
import ast
import re

# 🔐 OpenAI API 설정
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")) 

# 🎼 GPT로 8화음 시퀀스 8개 요청
response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "너는 명상 음악 작곡가야."},
        {"role": "user", "content": """
         감성적인 느낌의 8화음 2마디 길이 패턴을 16개 만들어줘. 파이썬 이중 리스트 형태로만 출력해줘. 예: [[\"C3\", \"E3\", ...], [...]]
         """}
    ]
)

# 🧠 GPT 응답에서 리스트 추출
raw_text = response.choices[0].message.content.strip()
match = re.search(r'\[\s*\[.*?\]\s*\]', raw_text, re.DOTALL)
if match:
    try:
        chord_list = ast.literal_eval(match.group(0))
    except Exception as e:
        print("⚠️ 파싱 실패:", e)
        chord_list = [["C3", "E3", "G3", "B3", "D4", "F4", "A4", "C5"]] * 8
else:
    print("⚠️ 리스트 추출 실패. 기본값 사용")
    chord_list = [["C3", "E3", "G3", "B3", "D4", "F4", "A4", "C5"]] * 8

print("🎼 GPT 생성 화음 리스트:")
for i, chord in enumerate(chord_list):
    print(f"  {i+1}화음: {chord}")

# 🎹 음 이름 → 주파수 테이블
note_freqs = {
    "C3": 130.81, "C#3": 138.59, "D3": 146.83, "D#3": 155.56,
    "E3": 164.81, "F3": 174.61, "F#3": 185.00, "G3": 196.00,
    "G#3": 207.65, "A3": 220.00, "A#3": 233.08, "B3": 246.94,
    "C4": 261.63, "C#4": 277.18, "D4": 293.66, "D#4": 311.13,
    "E4": 329.63, "F4": 349.23, "F#4": 369.99, "G4": 392.00,
    "G#4": 415.30, "A4": 440.00, "A#4": 466.16, "B4": 493.88,
    "C5": 523.25
}

# 🎵 음 생성 함수
def generate_note(freq, duration, volume=0.35):
    t = np.linspace(0, duration, int(44100 * duration), False)
    wave = np.sin(2 * np.pi * freq * t) * volume
    envelope = np.linspace(1, 0.1, len(wave))  # 간단한 페이드아웃
    return wave * envelope

# 🧘 전체 트랙 생성 (2마디당 8초씩 x 화음 수)
chord_duration = 8
sample_rate = 44100
total_wave = np.array([], dtype=np.float32)

for chord_notes in chord_list:
    freqs = [note_freqs[n] for n in chord_notes if n in note_freqs]
    if not freqs:
        continue
    chord_wave = sum(generate_note(f, chord_duration) for f in freqs)
    chord_wave /= np.max(np.abs(chord_wave))
    total_wave = np.concatenate((total_wave, chord_wave))

# 💽 저장 경로 및 파일명 정의
wav_path = "meditation.wav"
mp3_path = "meditation_output.mp3"
final_path = "sleepback.mp3"

# 🖊 WAV → MP3 저장
audio = np.int16(total_wave * 32767)
write(wav_path, sample_rate, audio)
AudioSegment.from_wav(wav_path).export(mp3_path, format="mp3")
os.remove(wav_path)

# 🌫 리버브 적용 (aecho 필터)
ffmpeg.input(mp3_path).output(
    final_path,
    af="aecho=0.8:0.9:1200|1800:0.3|0.25"
).run(overwrite_output=True)

print(f"✅ 최종 명상음악 MP3 생성 완료: {final_path}")
