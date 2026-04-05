import os, requests, random
from moviepy.editor import ImageClip, VideoFileClip, concatenate_videoclips, AudioFileClip, TextClip, CompositeVideoClip
from edge_tts import Communicate
from googleapiclient.discovery import build
from oauth2client.client import OAuth2Credentials

# ========== 1. Trending idea / hook ==========
print("🧠 Generating trending hook...")
try:
    # Example: use Pollinations text API (replace with actual prompt)
    poll_key = os.getenv("POLLINATIONS_API_KEY")
    prompt = "Write a short viral hook for a cute baby video: something like 'Wait until you see this baby laugh!'"
    headers = {"Authorization": f"Bearer {poll_key}"} if poll_key else {}
    resp = requests.post(
        "https://gen.pollinations.ai/v1/chat/completions",
        headers=headers,
        json={
            "model": "openai",
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    resp.raise_for_status()
    hook_text = resp.json()["choices"][0]["message"]["content"]
except Exception as e:
    hook_text = "Check this out!"
print("Hook:", hook_text)

# ========== 2. Fetch/Create Media ==========
os.makedirs("outputs", exist_ok=True)
media_path = None

# First try: Pollinations image generation
print("🖼 Fetching image via Pollinations...")
try:
    img_url = f"https://gen.pollinations.ai/image/{requests.utils.quote(hook_text)}"
    headers = {"Authorization": f"Bearer {poll_key}"} if poll_key else {}
    img_data = requests.get(img_url, headers=headers).content
    img_file = "outputs/bg.jpg"
    with open(img_file, "wb") as f: f.write(img_data)
    media_path = img_file
    print("Image saved to", img_file)
except Exception as e:
    print("Pollinations image failed:", e)

# If Pollinations failed or to use real video: fall back to Pexels video
if not media_path:
    print("📹 Fetching stock video via Pexels...")
    pexel_key = os.getenv("PEXELS_API_KEY")
    search = requests.get(
        "https://api.pexels.com/v1/videos/search",
        headers={"Authorization": pexel_key},
        params={"query": "cute baby", "per_page": 1}
    )
    data = search.json().get("videos", [])
    if data:
        video_url = data[0]["video_files"][0]["link"]
        res = requests.get(video_url)
        vid_file = "outputs/bg.mp4"
        with open(vid_file, "wb") as f: f.write(res.content)
        media_path = vid_file
        print("Video saved to", vid_file)
    else:
        raise RuntimeError("No Pexels video found")

# ========== 3. Audio (TTS voice + music) ==========
print("🎤 Generating voiceover audio...")
tts = Communicate(hook_text, voice="en-US-JennyNeural")
tts_task = tts.save("outputs/voice.mp3")
tts_task.get()  # run to completion

print("🎵 Adding background music...")
# Use a short free sound or silence as background (Volume mixed down)
bgm_url = "https://www.example.com/path/to/freesound.mp3"  # or use Pexels if available
try:
    res = requests.get(bgm_url)
    with open("outputs/music.mp3", "wb") as f: f.write(res.content)
    bgm_path = "outputs/music.mp3"
except Exception:
    bgm_path = None

# ========== 4. Compose video (5-8s) ==========
print("🎬 Editing video to 7 seconds and merging audio...")
clips = []
if media_path.endswith(".mp4"):
    clip = VideoFileClip(media_path).subclip(0, 7)
else:
    clip = ImageClip(media_path).set_duration(7)
# Add text overlay
txt = TextClip(hook_text, fontsize=48, color='white', font='Arial-Bold').set_pos('center').set_duration(3)
clip = CompositeVideoClip([clip, txt.set_position(('center','bottom'))])
clips.append(clip)

final_clip = concatenate_videoclips(clips)
# Attach audio (voice + bgm)
voice_audio = AudioFileClip("outputs/voice.mp3")
if bgm_path:
    bgm_audio = AudioFileClip(bgm_path).volumex(0.2).set_duration(final_clip.duration)
    combined_audio = CompositeAudioClip([bgm_audio, voice_audio.volumex(1.0)])
else:
    combined_audio = voice_audio
final_clip = final_clip.set_audio(combined_audio)
output_vid = "outputs/video.mp4"
final_clip.write_videofile(output_vid, fps=24)
print("Final video saved to", output_vid)

# ========== 5. Title/Description/Hashtags ==========
print("✍️ Generating title, description, hashtags...")
try:
    title_prompt = f"Generate an engaging YouTube title, description, and hashtags for a short video with hook: \"{hook_text}\""
    resp2 = requests.post(
        "https://gen.pollinations.ai/v1/chat/completions",
        headers=headers,
        json={"model": "openai", "messages": [{"role": "user", "content": title_prompt}]}
    )
    resp2.raise_for_status()
    full_text = resp2.json()["choices"][0]["message"]["content"]
    # Simple parse (expect format: Title: ... Description: ... Hashtags: ...)
    lines = full_text.splitlines()
    title = lines[0].replace("Title:", "").strip() if lines else ""
    description = lines[1].replace("Description:", "").strip() if len(lines)>1 else ""
    hashtags = lines[2].replace("Hashtags:", "").strip() if len(lines)>2 else ""
except Exception as e:
    title = hook_text[:50] + "..."
    description = ""
    hashtags = "#shorts #viral"
print("Title:", title)
print("Hashtags:", hashtags)

# ========== 6. Upload to YouTube ==========
print("📤 Uploading to YouTube...")
# OAuth2 credentials from secrets
credentials = OAuth2Credentials(
    access_token=None,
    client_id=os.getenv("YOUTUBE_CLIENT_ID"),
    client_secret=os.getenv("YOUTUBE_CLIENT_SECRET"),
    refresh_token=os.getenv("YOUTUBE_REFRESH_TOKEN"),
    token_expiry=None, token_uri="https://oauth2.googleapis.com/token",
    user_agent=None, revoke_uri=None, id_token=None, token_response=None
)
youtube = build('youtube', 'v3', credentials=credentials)

body = {
    "snippet": {
        "title": title,
        "description": description,
        "tags": [tag.strip("#") for tag in hashtags.split() if tag.startswith("#")],
        "categoryId": "22"  # 22 = People & Blogs (example)
    },
    "status": {"privacyStatus": "public"}
}
media = MediaFileUpload(output_vid, chunksize=-1, resumable=True, mimetype='video/mp4')
request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
response = request.execute()
print("✅ Uploaded video. Video ID:", response.get("id"))
