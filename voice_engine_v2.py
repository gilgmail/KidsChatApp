#!/usr/bin/env python3
"""
Voice Engine v2 — Gemini Live 持久 session + 對話記憶
  + 藍牙檢查（無藍牙則拒絕啟動）
  + 藍牙斷線自動關閉
  + 閒置 10 分鐘自動關閉（可調 IDLE_TIMEOUT_SEC）
  + 多模式：VOICE_MODE=chat|kids|english
  + kids 模式：說「唱歌」播 YouTube、說「掰掰」自動關閉
"""
import asyncio
import os
import shutil
import subprocess
import sys
import time

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types as gtypes

GOOGLE_API_KEY   = os.environ["GOOGLE_API_KEY"]
SAMPLE_RATE      = 16000
SILENCE_THRESH   = 0.015
SILENCE_SEC      = 0.6
MAX_SEC          = 12
IDLE_TIMEOUT_SEC = int(os.environ.get("VOICE_IDLE_TIMEOUT", "600"))
VOICE_MODE       = os.environ.get("VOICE_MODE", "chat")

YTDLP = shutil.which("yt-dlp") or os.path.expanduser("~/.local/bin/yt-dlp")

# 兒歌關鍵字 → YouTube 搜尋詞
SONG_MAP = {
    "小星星":   "小星星 兒歌",
    "生日快樂": "生日快樂歌",
    "兩隻老虎": "兩隻老虎 兒歌",
    "火車快飛": "火車快飛 兒歌",
    "蝴蝶":    "蝴蝶 兒歌",
    "拔蘿蔔":  "拔蘿蔔 兒歌",
    "愛你":    "我愛你 兒歌",
}

GOODBYE_WORDS = {"掰掰", "拜拜", "bye", "再見", "掰", "byebye", "bye bye", "goodbye"}

SYSTEMS = {
    "chat": (
        "你是繁體中文語音助理。必須用自然流暢的繁體中文口語回答。"
        "不使用任何書面格式或符號。說話像真人一樣。"
    ),
    "kids": (
        "你是一個陪伴2歲9個月女孩的玩伴。"
        "規則：每次只說一兩句，不要長篇大論。"
        "優先回應她說的話和需求，不要自己主導話題。"
        "她問問題就簡單回答。她想玩就陪她玩。"
        "她說跳舞就一起喊節奏或唱跳舞的歌。"
        "用最簡單的詞，多用疊字和擬聲詞。語氣溫柔活潑。"
        "不要主動出題考她，不要說教，不要問太多問題。"
        "如果她說唱歌，回答「好，幫你找！」就好，不要自己唱。"
    ),
    "english": (
        "You are a friendly English conversation coach. "
        "Speak only in English. Keep sentences natural and clear. "
        "If the user mispronounces a word, gently repeat it correctly in your response "
        "without making them feel embarrassed (e.g. 'Yes, that's a BEACH — great!'). "
        "Encourage every attempt. If the user speaks Chinese, kindly ask them to try in English. "
        "Keep responses short and conversational."
    ),
}

SYSTEM = SYSTEMS.get(VOICE_MODE, SYSTEMS["chat"])
MODE_NAMES = {"chat": "純聊天", "kids": "兒童對話（2y9m）", "english": "英文練習"}

LIVE_CONFIG = gtypes.LiveConnectConfig(
    response_modalities=["AUDIO"],
    system_instruction=SYSTEM,
    speech_config=gtypes.SpeechConfig(
        voice_config=gtypes.VoiceConfig(
            prebuilt_voice_config=gtypes.PrebuiltVoiceConfig(voice_name="Aoede")
        )
    ),
    realtime_input_config=gtypes.RealtimeInputConfig(
        automatic_activity_detection=gtypes.AutomaticActivityDetection(disabled=True)
    ),
)

client = genai.Client(api_key=GOOGLE_API_KEY)


# ── 藍牙檢查 ──────────────────────────────────────────────────────────────────

def bluetooth_connected() -> bool:
    try:
        out = subprocess.check_output(
            ["pactl", "list", "sinks", "short"], text=True, stderr=subprocess.DEVNULL
        )
        return "bluez" in out.lower()
    except Exception:
        return False


def require_bluetooth():
    if not bluetooth_connected():
        print("❌ 未偵測到藍牙音訊裝置，請先連接藍牙耳機或音箱後再啟動。", flush=True)
        sys.exit(1)
    print("✓ 藍牙裝置已連線", flush=True)


# ── 錄音 ──────────────────────────────────────────────────────────────────────

def record_until_silence() -> np.ndarray:
    frames: list[np.ndarray] = []
    silence_since: float | None = None
    started = False

    def cb(indata, _frames, _time, _status):
        nonlocal silence_since, started
        rms = float(np.sqrt(np.mean(indata ** 2)))
        frames.append(indata.copy())
        if rms > SILENCE_THRESH:
            started = True
            silence_since = None
        elif started and silence_since is None:
            silence_since = time.time()

    print("\n👂 聆聽中...", end="", flush=True)
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                        dtype="float32", callback=cb, device="pulse"):
        t0 = time.time()
        while True:
            time.sleep(0.05)
            if started and silence_since and time.time() - silence_since >= SILENCE_SEC:
                break
            if time.time() - t0 >= MAX_SEC:
                break

    return np.concatenate(frames).flatten() if frames else np.zeros(SAMPLE_RATE)


# ── kids 模式：STT + 意圖偵測 ─────────────────────────────────────────────────

_whisper_model = None

def get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper_model


def kids_stt(audio: np.ndarray) -> str:
    """快速 STT，用於偵測關鍵字（限前 6 秒避免卡住）"""
    try:
        short = audio[:SAMPLE_RATE * 6].astype(np.float32)
        # 音量放大 4 倍，補償藍牙麥克風偏小
        short = np.clip(short * 4.0, -1.0, 1.0)
        segs, _ = get_whisper().transcribe(
            short, language="zh", beam_size=3, vad_filter=False,
            condition_on_previous_text=False,
            initial_prompt="小孩說：唱歌、小星星、掰掰、跳舞、拜拜。"
        )
        result = "".join(s.text for s in segs).strip().lower()
        print(f"\n[Whisper raw: '{result}']", flush=True)
        return result
    except Exception as e:
        print(f"\n[Whisper error: {e}]", flush=True)
        return ""


def detect_song(text: str) -> str | None:
    """回傳 YouTube 搜尋詞，找不到歌名則用通用兒歌搜尋"""
    if "唱" not in text and "歌" not in text:
        return None
    for keyword, query in SONG_MAP.items():
        if keyword in text:
            return query
    return "好聽兒歌 台灣"


def detect_goodbye(text: str) -> bool:
    return any(w in text for w in GOODBYE_WORDS)


# ── YouTube 播歌 ──────────────────────────────────────────────────────────────

async def play_youtube_song(query: str):
    """用 yt-dlp 從 Bilibili 搜尋並播放，最多播 90 秒"""
    print(f"\n🎵 搜尋：{query}", flush=True)
    tmp = f"/tmp/kids_song_{int(time.time())}.mp3"
    try:
        dl = await asyncio.create_subprocess_exec(
            YTDLP, "-x", "--audio-format", "mp3",
            "--retries", "3",
            "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "--add-header", "Referer:https://www.bilibili.com/",
            "-o", tmp, f"bilisearch1:{query}",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(dl.wait(), timeout=120)
        except asyncio.TimeoutError:
            dl.kill()
            print("\n[歌曲下載逾時]", flush=True)
            return

        if not os.path.exists(tmp):
            print("\n[找不到歌曲]", flush=True)
            return

        print(f"\n▶ 播放中（最多 90 秒）", flush=True)
        ff = await asyncio.create_subprocess_exec(
            "ffmpeg", "-i", tmp, "-f", "s16le", "-ar", "24000", "-ac", "1", "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        ap = await asyncio.create_subprocess_exec(
            "aplay", "-q", "-D", "pulse", "-f", "S16_LE", "-r", "24000", "-c", "1",
            stdin=ff.stdout,
        )
        try:
            await asyncio.wait_for(ap.wait(), timeout=90)
        except asyncio.TimeoutError:
            ap.kill()
        ff.kill()
        print("\n[播放結束]", flush=True)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# ── 一輪對話 ──────────────────────────────────────────────────────────────────

async def one_turn(session, audio: np.ndarray):
    pcm  = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
    t0   = time.time()
    proc = None

    try:
        await session.send_realtime_input(activity_start=gtypes.ActivityStart())
        await session.send_realtime_input(
            audio=gtypes.Blob(data=pcm, mime_type="audio/pcm;rate=16000")
        )
        await session.send_realtime_input(activity_end=gtypes.ActivityEnd())

        first = True
        async for response in session.receive():
            audio_data = response.data
            if not audio_data and response.server_content:
                mt = response.server_content.model_turn
                if mt and mt.parts:
                    for part in mt.parts:
                        if part.inline_data and part.inline_data.data:
                            audio_data = part.inline_data.data
                            break

            if audio_data:
                if proc is None:
                    proc = subprocess.Popen(
                        ["aplay", "-q", "-D", "pulse", "-f", "S16_LE", "-r", "24000", "-c", "1"],
                        stdin=subprocess.PIPE,
                    )
                if first:
                    first = False
                    print(f"\n[首字 {time.time()-t0:.1f}s]", flush=True)
                try:
                    proc.stdin.write(audio_data)
                    proc.stdin.flush()
                except BrokenPipeError:
                    break

            sc = response.server_content
            if sc and (sc.turn_complete or sc.interrupted):
                print(f"\n[✓ {time.time()-t0:.1f}s]", flush=True)
                break

    except Exception as e:
        print(f"\n[turn 錯誤：{e}]", flush=True)
        raise
    finally:
        if proc and proc.returncode is None:
            proc.stdin.close()
            proc.wait()


# ── 主迴圈 ────────────────────────────────────────────────────────────────────

async def main():
    loop = asyncio.get_event_loop()
    mode_label = MODE_NAMES.get(VOICE_MODE, VOICE_MODE)
    print(f"語音助理 v2 已啟動（Ctrl+C 離開）  模式：{mode_label}")
    print(f"持久 session + 對話記憶 | 閒置 {IDLE_TIMEOUT_SEC//60} 分鐘自動關閉")
    print("-" * 45)

    while True:
        try:
            async with client.aio.live.connect(
                model="gemini-3.1-flash-live-preview", config=LIVE_CONFIG
            ) as session:
                print("Gemini 連線成功")
                last_active = time.time()

                while True:
                    if time.time() - last_active > IDLE_TIMEOUT_SEC:
                        print(f"\n[閒置超過 {IDLE_TIMEOUT_SEC//60} 分鐘，自動關閉]", flush=True)
                        return

                    if not bluetooth_connected():
                        print("\n[藍牙斷線，自動關閉]", flush=True)
                        return

                    audio = await loop.run_in_executor(None, record_until_silence)
                    if len(audio) < SAMPLE_RATE * 0.3:
                        continue

                    last_active = time.time()

                    # kids 模式：偵測唱歌 / 掰掰
                    if VOICE_MODE == "kids":
                        # 能量太低表示沒有真實語音，跳過 Whisper 避免幻覺
                        rms = float(np.sqrt(np.mean(audio ** 2)))
                        if rms < 0.004:
                            await one_turn(session, audio)
                            continue
                        text = await loop.run_in_executor(None, kids_stt, audio)
                        print(f"\n[識別：{text}]", flush=True)

                        if detect_goodbye(text):
                            print("\n[掰掰，自動關閉]", flush=True)
                            return

                        song_query = detect_song(text)
                        if song_query:
                            await play_youtube_song(song_query)
                            continue  # 跳過 Gemini，直接回到錄音

                    await one_turn(session, audio)

        except KeyboardInterrupt:
            print("\n再見！")
            return
        except Exception as e:
            print(f"\n[session 斷線：{e}，3s 後重連]", flush=True)
            await asyncio.sleep(3)


if __name__ == "__main__":
    require_bluetooth()
    asyncio.run(main())
