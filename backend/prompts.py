"""
KidsChatApp — System Prompts & Game Mode Definitions
"""

import os

# ── System Prompt（從 system_prompt.txt 載入，修改後重啟生效）──
_PROMPT_FILE = os.path.join(os.path.dirname(__file__), "system_prompt.txt")

_FALLBACK_PROMPT = "你是一個友善的幼兒對話夥伴，用繁體中文回答，每次最多15個字，結尾加一個問題。"

def _load_system_prompt() -> str:
    try:
        with open(_PROMPT_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return _FALLBACK_PROMPT

SYSTEM_PROMPT = _load_system_prompt()

# ── 模式清單 ────────────────────────────────────────────────
GAME_MODES: dict[str, str] = {
    "free":          "💬 自由聊天",
    "animal_quiz":   "🐾 猜動物",
    "color_shape":   "🔴 顏色形狀",
    "counting":      "🔢 數數字",
    "story":         "📖 互動故事",
    "sing":          "🎵 唱兒歌",
    "daily_english": "🔤 英文小教室",
    "emotion":       "😊 情緒小學堂",
}


# ── 模式 prefix（注入在訊息前，引導 AI 進入對應模式）──────────
MODE_PREFIXES: dict[str, str] = {
    "free":          "【自由聊天】",
    "animal_quiz":   "【猜動物】",
    "color_shape":   "【顏色形狀】",
    "counting":      "【數數字】",
    "story":         "【互動故事】",
    "sing":          "【唱兒歌】",
    "daily_english": "【英文小教室】",
    "emotion":       "【情緒小學堂】",
    # 向下相容舊 mode 名稱
    "chat":          "【自由聊天】",
    "roleplay":      "【互動故事】",
}

# ── 每個遊戲的開場白 ──────────────────────────────────────────
GAME_OPENERS: dict[str, str] = {
    "free":          "嗨嗨～我是小老師！😊 你今天想聊什麼呀？",
    "animal_quiz":   "我想到了一隻動物！牠有四條腿，毛毛的，很喜歡吃草。你猜是誰呀？🐾",
    "color_shape":   "我們來玩顏色遊戲！找找看，身邊有沒有紅色的東西？指給小老師看！🔴",
    "counting":      "我們來數數字好不好？🔢 伸出你的小手手，跟我一起數！一……",
    "story":         "📖 從前從前，有一隻小兔兔迷路了！牠要往左邊走，還是右邊走？你幫牠決定！",
    "sing":          "🎵 我們來唱小星星！跟我唱：小星星，亮晶晶～準備好了嗎？",
    "daily_english": "🔤 今天學一個英文！這是「apple」，就是蘋果的意思！跟我說：apple～",
    "emotion":       "😊 你現在感覺怎麼樣呀？開心嗎？還是有一點點累累的？",
}

WELCOME_MESSAGE = (
    "嗨嗨～我是小老師！😊 "
    "你今天想唱歌歌，還是聽故事呢？"
)
