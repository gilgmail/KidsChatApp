#!/usr/bin/env python3
"""
Voice Engine — Gemini Live（每輪獨立 session）
  + 對話歷史（send_client_content 注入）
  + 播放中可打斷
"""
import asyncio
import os
import subprocess
import time

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from google import genai
from google.genai import types as gtypes

GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
SAMPLE_RATE    = 16000
SILENCE_THRESH = 0.015
SILENCE_SEC    = 0.5
MAX_SEC        = 15
MAX_HISTORY    = 5

SYSTEM = (
    "你是繁體中文語音助理。必須用自然流暢的繁體中文口語回答。"
    "不使用任何書面格式或符號。說話像真人一樣。"
)

def make_live_config(history: list[tuple[str, str]]) -> gtypes.LiveConnectConfig:
    sys_text = SYSTEM
    if history:
        lines = []
        for u, a in history[-3:]:
            lines.append(f"用戶：{u}")
            lines.append(f"你：{a if a else '（已回應）'}")
        sys_text += "\n\n[最近對話記錄]\n" + "\n".join(lines) + "\n[繼續對話]"
    return gtypes.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=sys_text,
        speech_config=gtypes.SpeechConfig(
            voice_config=gtypes.VoiceConfig(
                prebuilt_voice_config=gtypes.PrebuiltVoiceConfig(voice_name="Aoede")
            )
        ),
        realtime_input_config=gtypes.RealtimeInputConfig(
            automatic_activity_detection=gtypes.AutomaticActivityDetection(disabled=True)
        ),
    )

client  = genai.Client(api_key=GOOGLE_API_KEY)
whisper = WhisperModel("base", device="cpu", compute_type="int8")


# ── 錄音 ────────────────────────────────────────────────────────────────────

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

    print("👂 聆聽中...", end="", flush=True)
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


# ── 本地 Whisper STT ─────────────────────────────────────────────────────────

def local_stt(audio: np.ndarray) -> str:
    segs, _ = whisper.transcribe(
        audio, language="zh", beam_size=1, vad_filter=True,
        condition_on_previous_text=False, initial_prompt="這是一段日常中文對話。",
    )
    return "".join(s.text for s in segs).strip()


# ── 一輪對話 ─────────────────────────────────────────────────────────────────

async def one_turn(audio: np.ndarray, history: list[tuple[str, str]]) -> str:
    """回傳 user_text（播完後才跑 Whisper，不佔 Gemini 時間）"""
    loop = asyncio.get_event_loop()
    pcm  = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
    t0   = time.time()

    proc           = None
    mic_stream     = None
    interrupt_flag = [False]
    interrupt_count= [0]
    playback_start = [0.0]

    def interrupt_cb(indata, _frames, _time, _status):
        if not interrupt_flag[0]:
            if time.time() - playback_start[0] < 1.0:
                return
            rms = float(np.sqrt(np.mean(indata ** 2)))
            if rms > SILENCE_THRESH * 8:
                interrupt_count[0] += 1
                if interrupt_count[0] >= 5:
                    interrupt_flag[0] = True
            else:
                interrupt_count[0] = 0

    try:
        async with client.aio.live.connect(
            model="gemini-3.1-flash-live-preview", config=make_live_config(history)
        ) as session:

            # 送出本輪音訊
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
                        mic_stream = sd.InputStream(
                            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                            callback=interrupt_cb, blocksize=int(SAMPLE_RATE * 0.1),
                            device="pulse",
                        )
                        mic_stream.start()
                        playback_start[0] = time.time()
                    if first:
                        first = False
                        print(f"\n[首字 {time.time()-t0:.1f}s]", flush=True)
                    try:
                        proc.stdin.write(audio_data)
                        proc.stdin.flush()
                    except BrokenPipeError:
                        break

                    if interrupt_flag[0]:
                        print("\n[⚡ 打斷]", flush=True)
                        proc.stdin.close()
                        proc.terminate()
                        proc.wait()
                        proc = None
                        break

                sc = response.server_content
                if sc and (sc.turn_complete or sc.interrupted):
                    print(f"\n[✓ {time.time()-t0:.1f}s]", flush=True)
                    break

    except Exception as e:
        print(f"\n[session 錯誤：{e}]", flush=True)
    finally:
        if mic_stream:
            mic_stream.stop()
            mic_stream.close()
        if proc and proc.returncode is None:
            proc.stdin.close()
            proc.wait()

    # Whisper 在 Gemini 回應結束後才跑，不搶資源
    # 截短至 8 秒，避免長音訊卡死
    stt_audio = audio[:SAMPLE_RATE * 8]
    try:
        user_text = await asyncio.wait_for(
            loop.run_in_executor(None, local_stt, stt_audio),
            timeout=10.0
        )
    except asyncio.TimeoutError:
        print("\n[STT 超時]", flush=True)
        user_text = ""
    return user_text


# ── 主迴圈 ───────────────────────────────────────────────────────────────────

async def main():
    loop    = asyncio.get_event_loop()
    history: list[tuple[str, str]] = []

    print("語音助理已啟動（Ctrl+C 離開）")
    print("模式：Gemini Live + 對話歷史 + 打斷支援")
    print("-" * 45)

    while True:
        try:
            audio = await loop.run_in_executor(None, record_until_silence)
            if len(audio) < SAMPLE_RATE * 0.3:
                continue

            user_text = await one_turn(audio, history)

            if user_text:
                history.append((user_text, ""))
                if len(history) > MAX_HISTORY:
                    history.pop(0)
                print(f"你：{user_text}", flush=True)

        except KeyboardInterrupt:
            print("\n再見！")
            break


if __name__ == "__main__":
    asyncio.run(main())
