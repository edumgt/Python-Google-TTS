# client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY"))  # 여기에 API 키 입력
from openai import OpenAI
from gtts import gTTS
import ffmpeg
import os
import shlex

# 1️⃣ OpenAI GPT 설정
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY"))  # 여기에 API 키 입력

# 2️⃣ GPT 프롬프트 (촬영 기사 스타일로 응답 유도)
scene_description = "바다의 잔잔한 파도를 촬영합니다."
response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "당신은 프로 영상 촬영기사입니다. 사용자의 요청에 따라 실제 현장에서 촬영 지시나 콘티 스타일로 작성해 주세요."},
        {"role": "user", "content": f"'{scene_description}' 장면을 촬영해야 해요. 어떻게 구성할까요?"}
    ]
)

story = response.choices[0].message.content.strip()
print("🎥 GPT 촬영 시나리오:\n", story)

# 3️⃣ gTTS 음성 생성
tts = gTTS(text=story, lang='ko')
audio_file = "voice.mp3"
tts.save(audio_file)

# 4️⃣ 배경 영상 생성 (정적 컬러 or 추후 배경 영상으로 대체 가능)
video_file = "blank.mp4"
ffmpeg.input("color=c=black:s=1280x720:d=20", f='lavfi') \
    .output(video_file, vcodec='libx264', pix_fmt='yuv420p') \
    .run(overwrite_output=True)

# 5️⃣ 자막용 텍스트 → 촬영 키워드 요약 (예: 카메라 무브먼트 요약)
short_text = "드론으로 수평 이동하며 파도 클로즈업"  # 필요시 요약 자동화 가능
safe_text = shlex.quote(short_text)

video_with_text = "text_overlay.mp4"
ffmpeg.input(video_file).output(
    video_with_text,
    vf=f"drawtext=fontfile='/Windows/Fonts/Arial.ttf':text={safe_text}:" +
       "fontcolor=white:fontsize=36:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.5",
    vcodec='libx264'
).run(overwrite_output=True)

# 6️⃣ 영상 + 음성 합성
final_output = "sleeptest.mp4"
ffmpeg.input(video_with_text).output(
    final_output,
    i=audio_file,
    vcodec='copy',
    acodec='aac',
    shortest=None
).run(overwrite_output=True)

print(f"✅ 촬영기사 스타일 영상 생성 완료: {final_output}")
