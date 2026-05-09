#!/usr/bin/env python3
"""
自動化語音助理評估腳本
  - 依序送出測試 WAV → Gemini Live 持久 session
  - 捕捉音訊回應 → Whisper 轉文字
  - 檢查關鍵字，輸出 PASS / FAIL
"""
import asyncio
import csv
import os
import time
import wave
from io import BytesIO

import numpy as np
from faster_whisper import WhisperModel
from google import genai
from google.genai import types as gtypes

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "AIzaSyDweqkUmPyNzmUPTN9Y8mE2Su7lD8uD8VY")
TESTS_DIR = os.path.expanduser("~/hermes-workspace/tests")
RESULT_CSV = os.path.expanduser("~/hermes-workspace/eval_result.csv")

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

# (id, 說明, wav檔, 必須包含的關鍵字, 備註)
TEST_CASES = [
    ("T01", "記憶建立", "01_memory_setup.wav",   [],               "說出名字小明"),
    ("T02", "記憶召回", "02_memory_recall.wav",  ["小明"],         "應記得名字"),
    ("T03", "上下文跟隨","03_context_follow.wav", ["小明", "十歲"], "應記得內容"),
    ("T04", "簡單問答", "04_simple_qa.wav",       [],               "有回應即可"),
    ("T05", "天氣問答", "05_weather.wav",         [],               "有回應即可"),
]

client  = genai.Client(api_key=GOOGLE_API_KEY)
whisper = WhisperModel("base", device="cpu", compute_type="int8")


def load_wav_pcm(path: str) -> bytes:
    """讀取 16kHz mono WAV，回傳 int16 PCM bytes"""
    with wave.open(path, "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        sr = wf.getframerate()
        ch = wf.getnchannels()
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    # resample to 16kHz if needed
    if sr != 16000:
        ratio = 16000 / sr
        new_len = int(len(audio) * ratio)
        audio = np.interp(np.linspace(0, len(audio), new_len), np.arange(len(audio)), audio)
    return (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


def stt_on_response(audio_chunks: list[bytes]) -> str:
    """對 24kHz PCM 回應音訊跑 Whisper（downsample to 16kHz）"""
    if not audio_chunks:
        return ""
    raw = b"".join(audio_chunks)
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32767.0
    # downsample 24kHz → 16kHz
    new_len = int(len(audio) * 16000 / 24000)
    audio16 = np.interp(np.linspace(0, len(audio), new_len), np.arange(len(audio)), audio).astype(np.float32)
    segs, _ = whisper.transcribe(
        audio16, language="zh", beam_size=1, vad_filter=True,
        condition_on_previous_text=False
    )
    return "".join(s.text for s in segs).strip()


async def run_one_turn(session, pcm: bytes, timeout: float = 15.0) -> tuple[str, float, list[bytes]]:
    """送出一輪音訊，回傳 (response_text, latency_first, audio_chunks)"""
    t0 = time.time()
    first_latency = None
    audio_chunks: list[bytes] = []

    await session.send_realtime_input(activity_start=gtypes.ActivityStart())
    await session.send_realtime_input(
        audio=gtypes.Blob(data=pcm, mime_type="audio/pcm;rate=16000")
    )
    await session.send_realtime_input(activity_end=gtypes.ActivityEnd())

    try:
        async with asyncio.timeout(timeout):
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
                    if first_latency is None:
                        first_latency = time.time() - t0
                    audio_chunks.append(audio_data)

                sc = response.server_content
                if sc and (sc.turn_complete or sc.interrupted):
                    break
    except TimeoutError:
        pass

    # Whisper on response (with STT timeout)
    loop = asyncio.get_event_loop()
    try:
        resp_text = await asyncio.wait_for(
            loop.run_in_executor(None, stt_on_response, audio_chunks),
            timeout=12.0
        )
    except asyncio.TimeoutError:
        resp_text = "[STT 超時]"

    return resp_text, first_latency or 0.0, audio_chunks


async def main():
    print("=== 語音助理自動化評估 ===\n")
    results = []

    async with client.aio.live.connect(
        model="gemini-3.1-flash-live-preview", config=LIVE_CONFIG
    ) as session:
        print("Gemini 連線成功，開始測試...\n")

        for tid, desc, wav_file, keywords, note in TEST_CASES:
            wav_path = os.path.join(TESTS_DIR, wav_file)
            if not os.path.exists(wav_path):
                print(f"  {tid} [{desc}] ⚠️  找不到 {wav_file}")
                continue

            print(f"  {tid} [{desc}]", end=" ", flush=True)
            pcm = load_wav_pcm(wav_path)

            try:
                resp_text, latency, _ = await run_one_turn(session, pcm)
            except Exception as e:
                print(f"❌ 錯誤：{e}")
                results.append([tid, desc, "ERROR", "", 0, note])
                continue

            # 判斷通過條件
            if not keywords:
                passed = bool(resp_text)  # 有任何回應即通過
            else:
                passed = any(kw in resp_text for kw in keywords)

            status = "PASS" if passed else "FAIL"
            print(f"[首字 {latency:.1f}s] {status}")
            print(f"         回應：{resp_text[:80] if resp_text else '（無）'}")
            results.append([tid, desc, status, resp_text, f"{latency:.1f}", note])

            await asyncio.sleep(0.5)  # 輪次間短暫停頓

    # 寫入 CSV
    with open(RESULT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ID", "說明", "結果", "回應文字", "首字延遲(s)", "備註"])
        w.writerows(results)

    passed = sum(1 for r in results if r[2] == "PASS")
    print(f"\n結果：{passed}/{len(results)} 通過 → {RESULT_CSV}")


if __name__ == "__main__":
    asyncio.run(main())
