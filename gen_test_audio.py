#!/usr/bin/env python3
"""產生測試用中文語音檔（使用 edge-tts）"""
import asyncio
import os
import subprocess

import edge_tts

TEST_CASES = [
    ("01_memory_setup",   "你好，我叫小明，我今年十歲"),
    ("02_memory_recall",  "你記得我叫什麼名字嗎"),
    ("03_context_follow", "我剛才說了什麼"),
    ("04_simple_qa",      "現在幾點"),
    ("05_weather",        "今天台北天氣怎麼樣"),
    ("06_interrupt_say",  "等一下，我想問你另一個問題"),
]

OUTPUT_DIR = os.path.expanduser("~/hermes-workspace/tests")
VOICE = "zh-TW-HsiaoChenNeural"


async def gen(name: str, text: str):
    mp3_path = f"{OUTPUT_DIR}/{name}.mp3"
    wav_path = f"{OUTPUT_DIR}/{name}.wav"
    comm = edge_tts.Communicate(text, VOICE, rate="+10%")
    await comm.save(mp3_path)
    # 轉成 16kHz mono WAV（sounddevice/aplay 用）
    subprocess.run(
        ["ffmpeg", "-y", "-i", mp3_path,
         "-ar", "16000", "-ac", "1", wav_path],
        capture_output=True
    )
    os.remove(mp3_path)
    print(f"  ✓ {name}.wav — {text}")


async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"產生測試音訊到 {OUTPUT_DIR}/")
    for name, text in TEST_CASES:
        await gen(name, text)
    print("完成")


if __name__ == "__main__":
    asyncio.run(main())
