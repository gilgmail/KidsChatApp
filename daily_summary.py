#!/usr/bin/env python3
"""
KidsChatApp — 每日對話摘要 & 週報產生器

用法：
  python daily_summary.py              # 今天的摘要
  python daily_summary.py 2026-04-06   # 指定日期
  python daily_summary.py --week       # 最近 7 天週報
  python daily_summary.py --week 2026-04-06  # 指定結束日的週報
"""

import os
import sys
import json
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

from datetime import datetime, timedelta
from collections import Counter

import google.generativeai as genai

# ── 路徑設定 ─────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
LOG_DIR      = os.path.join(SCRIPT_DIR, "logs")
SUMMARY_DIR  = os.path.join(SCRIPT_DIR, "summaries")
os.makedirs(SUMMARY_DIR, exist_ok=True)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

GAME_MODE_NAMES = {
    "free":          "💬 自由聊天",
    "animal_quiz":   "🐾 猜動物",
    "color_shape":   "🔴 顏色形狀",
    "counting":      "🔢 數數字",
    "story":         "📖 互動故事",
    "sing":          "🎵 唱兒歌",
    "daily_english": "🔤 英文小教室",
    "emotion":       "😊 情緒小學堂",
}


# ── 日誌讀取 ─────────────────────────────────────────────────

def load_log(date_str: str) -> list:
    path = os.path.join(LOG_DIR, f"{date_str}.jsonl")
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


# ── 統計計算 ─────────────────────────────────────────────────

def compute_stats(entries: list) -> dict:
    if not entries:
        return {"total_turns": 0, "time_start": "N/A", "time_end": "N/A",
                "modes_used": {}, "kid_total_chars": 0, "kid_avg_chars": 0,
                "longest_kid_msg": "", "kid_messages": [], "reply_messages": []}

    modes = Counter()
    kid_words, reply_words, timestamps = [], [], []

    for e in entries:
        msg   = e.get("message", "")
        reply = e.get("reply", "")
        mode  = e.get("mode", "free")

        if msg.startswith("["):          # 系統事件（MODE_SWITCH 等）
            continue

        modes[mode] += 1
        kid_words.append(msg)
        reply_words.append(reply)
        if "time" in e:
            timestamps.append(e["time"])

    t_start = timestamps[0][:19]  if timestamps else "N/A"
    t_end   = timestamps[-1][:19] if timestamps else "N/A"
    total   = len(kid_words)

    return {
        "total_turns":     total,
        "time_start":      t_start,
        "time_end":        t_end,
        "modes_used":      dict(modes),
        "kid_total_chars": len("".join(kid_words)),
        "kid_avg_chars":   round(len("".join(kid_words)) / max(total, 1), 1),
        "longest_kid_msg": max(kid_words, key=len) if kid_words else "",
        "kid_messages":    kid_words,
        "reply_messages":  reply_words,
    }


# ── AI 摘要 ─────────────────────────────────────────────────

def _ai_model():
    if not GEMINI_API_KEY:
        raise RuntimeError("未設定 GEMINI_API_KEY")
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel(GEMINI_MODEL)


def generate_daily_summary(entries: list, stats: dict, date_str: str) -> str:
    if not GEMINI_API_KEY:
        return "[跳過 AI 摘要：未設定 GEMINI_API_KEY]"

    conv = ""
    for e in entries[:100]:
        msg   = e.get("message", "")
        reply = e.get("reply", "")
        if msg.startswith("["):
            conv += f"[系統: {msg}]\n"
        else:
            conv += f"👧 小孩: {msg}\n🌟 老師: {reply}\n\n"

    modes_display = {GAME_MODE_NAMES.get(k, k): v for k, v in stats["modes_used"].items()}

    prompt = f"""你是一位幼兒發展觀察專家。以下是一個三歲小女孩在 {date_str} 與 AI 語音助手的對話紀錄。
請產生一份給家長看的每日報告：

## 📅 {date_str} 每日對話報告

### 🎯 今日摘要
（2-3 句話總結今天的互動狀況）

### 🎮 活動紀錄
（她今天玩了哪些遊戲模式、各玩多久，以及整體參與度）

### 🗣️ 語言發展觀察
（今天說了哪些比較完整的句子、新詞彙、表達能力的亮點）

### 🧠 認知發展觀察
（她答對了什麼、對什麼有興趣、理解力表現）

### 😊 情緒與社交
（她的情緒狀態、互動意願、特別開心或抗拒的時刻）

### 💡 給爸爸媽媽的建議
（基於今天互動，建議接下來可以怎麼延伸、在生活中加強什麼）

### 📊 數據
- 對話輪數：{stats['total_turns']}
- 時間段：{stats['time_start']} ~ {stats['time_end']}
- 小孩平均每句字數：{stats['kid_avg_chars']}
- 最長的一句話：「{stats['longest_kid_msg']}」
- 使用的遊戲模式：{json.dumps(modes_display, ensure_ascii=False)}

---
完整對話紀錄：

{conv}

注意：
- 用繁體中文
- 語氣親切專業，像幼兒園老師寫給家長的聯絡簿
- 如果對話太少無法判斷，如實說明
"""
    model = _ai_model()
    return model.generate_content(prompt).text


def generate_weekly_report(end_date: str = None) -> str:
    if not GEMINI_API_KEY:
        return "[跳過 AI 週報：未設定 GEMINI_API_KEY]"

    end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()

    weekly_stats, all_kid_msgs = [], []
    for i in range(7):
        d = (end - timedelta(days=i)).strftime("%Y-%m-%d")
        entries = load_log(d)
        s = compute_stats(entries)
        s["date"] = d
        weekly_stats.append(s)
        all_kid_msgs.extend(s.get("kid_messages", []))

    start_str = (end - timedelta(days=6)).strftime("%m/%d")
    end_str   = end.strftime("%m/%d")

    prompt = f"""你是幼兒發展觀察專家。以下是一個三歲小女孩過去 7 天與 AI 語音助手的互動統計。
請產生一份週報：

## 📈 週報（{start_str} ~ {end_str}）

### 本週總覽
（互動頻率趨勢、總對話輪數、最活躍的日子）

### 語言發展趨勢
（平均句子長度是否增加、新詞彙量、表達完整度變化）

### 最愛的遊戲模式
（哪些模式玩最多、參與度最高）

### 本週亮點
（最有趣的互動、最大的進步）

### 下週建議
（建議嘗試的新活動、可以加強的方向）

數據：
{json.dumps(weekly_stats, ensure_ascii=False, indent=2)}

小孩所有發言（供語言分析）：
{json.dumps(all_kid_msgs[:200], ensure_ascii=False)}

用繁體中文，語氣親切專業。
"""
    model = _ai_model()
    return model.generate_content(prompt).text


# ── 主程式 ──────────────────────────────────────────────────

def main():
    # 週報模式
    if len(sys.argv) > 1 and sys.argv[1] == "--week":
        date_arg = sys.argv[2] if len(sys.argv) > 2 else None
        print("📊 產生週報中…\n")
        report = generate_weekly_report(date_arg)
        print(report)
        fname    = f"weekly_{datetime.now().strftime('%Y-%m-%d')}.md"
        out_path = os.path.join(SUMMARY_DIR, fname)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n✅ 週報已儲存：{out_path}")
        return

    # 單日摘要
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    print(f"📋 載入 {date_str} 的對話紀錄…\n")

    entries = load_log(date_str)
    if not entries:
        print(f"⚠️  找不到 {date_str} 的紀錄")
        print(f"   路徑：{LOG_DIR}/{date_str}.jsonl")
        return

    stats = compute_stats(entries)
    modes_display = {GAME_MODE_NAMES.get(k, k): v for k, v in stats["modes_used"].items()}

    print("📊 基本統計：")
    print(f"   對話輪數：{stats['total_turns']}")
    print(f"   時間段：{stats['time_start']} ~ {stats['time_end']}")
    print(f"   小孩平均每句字數：{stats['kid_avg_chars']}")
    print(f"   遊戲模式：{json.dumps(modes_display, ensure_ascii=False)}")
    print(f"   最長的一句話：「{stats['longest_kid_msg']}」")
    print()

    print("🤖 產生 AI 摘要中…\n")
    summary = generate_daily_summary(entries, stats, date_str)
    print(summary)

    out_path = os.path.join(SUMMARY_DIR, f"{date_str}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"\n✅ 摘要已儲存：{out_path}")


if __name__ == "__main__":
    main()
