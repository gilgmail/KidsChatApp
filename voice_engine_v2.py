#!/usr/bin/env python3
"""
Voice Engine v2 — Gemini Live 持久 session + 對話記憶
  + 藍牙檢查（無藍牙則拒絕啟動）
  + 藍牙斷線自動關閉
  + 閒置 10 分鐘自動關閉（可調 IDLE_TIMEOUT_SEC）
"""
import asyncio
import os
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
IDLE_TIMEOUT_SEC = int(os.environ.get("VOICE_IDLE_TIMEOUT", "600"))  # 預設 10 分鐘

SYSTEM = (
    "你是繁體中文語音助理。必須用自然流暢的繁體中文口語回答。"
    "不使用任何書面格式或符號。說話像真人一樣。"
)

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
    """檢查是否有藍牙音訊裝置（sink）已連線"""
    try:
        out = subprocess.check_output(
            ["pactl", "list", "sinks", "short"], text=True, stderr=subprocess.DEVNULL
        )
        return "bluez" in out.lower()
    except Exception:
        return False


def require_bluetooth():
    """啟動時檢查藍牙，未連線則印出錯誤並退出"""
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
                        ["aplay", "-q", "-f", "S16_LE", "-r", "24000", "-c", "1"],
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
    print("語音助理 v2 已啟動（Ctrl+C 離開）")
    print(f"模式：持久 session + 對話記憶 | 閒置 {IDLE_TIMEOUT_SEC//60} 分鐘自動關閉")
    print("-" * 45)

    while True:
        try:
            async with client.aio.live.connect(
                model="gemini-3.1-flash-live-preview", config=LIVE_CONFIG
            ) as session:
                print("Gemini 連線成功")
                last_active = time.time()

                while True:
                    # 閒置逾時檢查
                    if time.time() - last_active > IDLE_TIMEOUT_SEC:
                        print(f"\n[閒置超過 {IDLE_TIMEOUT_SEC//60} 分鐘，自動關閉]", flush=True)
                        return

                    # 藍牙斷線檢查（每輪）
                    if not bluetooth_connected():
                        print("\n[藍牙斷線，自動關閉]", flush=True)
                        return

                    audio = await loop.run_in_executor(None, record_until_silence)
                    if len(audio) < SAMPLE_RATE * 0.3:
                        continue

                    last_active = time.time()
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
