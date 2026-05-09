#!/usr/bin/env python3
"""
Voice Engine v2 — Gemini Live 持久 session + 對話記憶
每輪錄音 + activity_start/end，穩定可靠
"""
import asyncio
import os
import subprocess
import time

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types as gtypes

GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
SAMPLE_RATE    = 16000
SILENCE_THRESH = 0.015
SILENCE_SEC    = 0.6
MAX_SEC        = 12

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


async def one_turn(session, audio: np.ndarray):
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
    t0  = time.time()
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


async def main():
    loop = asyncio.get_event_loop()
    print("語音助理 v2 已啟動（Ctrl+C 離開）")
    print("模式：持久 session + 對話記憶")
    print("-" * 45)

    while True:
        try:
            async with client.aio.live.connect(
                model="gemini-3.1-flash-live-preview", config=LIVE_CONFIG
            ) as session:
                print("Gemini 連線成功")
                while True:
                    audio = await loop.run_in_executor(None, record_until_silence)
                    if len(audio) < SAMPLE_RATE * 0.3:
                        continue
                    await one_turn(session, audio)

        except KeyboardInterrupt:
            print("\n再見！")
            return
        except Exception as e:
            print(f"\n[session 斷線：{e}，3s 後重連]", flush=True)
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
