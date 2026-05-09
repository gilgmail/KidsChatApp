
import asyncio
import os
import openai
import edge_tts
import speech_recognition as sr

# --- 1. 配置 ---
# 將你的 OpenAI API Key 填入此處。如果留空，程式將以「鸚鵡模式」運行。
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "") 

VOICES = {"child": "zh-TW-HsiaoChenNeural", "english": "en-US-JennyNeural"}
PROMPTS = {
    "child": "你是一位頂級的幼兒啟蒙老師，溫柔且充滿耐心。請用簡單、活潑、正向的中文，引導一位2歲9個月的小朋友探索世界。你的回答必須非常簡短（盡量控制在15個字以內），多用問句，並充滿童趣。",
    "english": "You are a professional and friendly English language tutor. Engage in a natural, flowing conversation with me. Keep your responses concise and clear, providing corrections or feedback only when necessary to maintain the flow."
}
SENTENCE_TERMINATORS = [".", "!", "?", "。", "！", "？", "\n"]

class VoiceEngine:
    def __init__(self, mode="child"):
        self.api_key_available = bool(OPENAI_API_KEY)
        self.client = None
        if self.api_key_available:
            self.client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        else:
            print("--- 警告：未找到 OpenAI API Key。將以「鸚鵡模式」啟動。---")
        
        self.mode = mode
        self.voice = VOICES[mode]
        self.system_prompt = PROMPTS[mode]
        self.tts_tasks = []
        
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        print("正在校準麥克風，請保持安靜...")
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=2)
        print("麥克風已準備就緒。")

    async def _play_audio_stream(self, tts_stream):
        try:
            proc = await asyncio.create_subprocess_exec(
                'ffplay', '-nodisp', '-autoexit', '-i', '-',
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
            )
            async for chunk in tts_stream:
                if chunk["type"] == "audio":
                    proc.stdin.write(chunk["data"])
            await proc.stdin.drain()
            proc.stdin.close()
            await proc.wait()
        except Exception as e:
            print(f"音訊播放時發生錯誤: {e}")

    async def _trigger_tts(self, sentence):
        sentence_to_speak = sentence.strip()
        if not sentence_to_speak: return
        print(f"機器人: {sentence_to_speak}")
        communicate = edge_tts.Communicate(sentence_to_speak, self.voice)
        task = asyncio.create_task(self._play_audio_stream(communicate.stream()))
        self.tts_tasks.append(task)

    async def _process_llm_stream(self, user_input):
        buffer = ""
        stream = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": self.system_prompt}, {"role": "user", "content": user_input}],
            stream=True
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                buffer += content
                for terminator in SENTENCE_TERMINATORS:
                    if terminator in buffer:
                        parts = buffer.split(terminator, 1)
                        await self._trigger_tts(parts[0] + terminator)
                        buffer = parts[1]
        if buffer: await self._trigger_tts(buffer)
        if self.tts_tasks: await asyncio.gather(*self.tts_tasks); self.tts_tasks = []

    async def listen_for_voice(self):
        loop = asyncio.get_running_loop()
        print("\n你可以說話了...")
        with self.microphone as source:
            try:
                audio = await loop.run_in_executor(None, self.recognizer.listen, source, 5, 5)
            except sr.WaitTimeoutError: return ""
        print("正在辨識...")
        try:
            text = await loop.run_in_executor(None, lambda: self.recognizer.recognize_google(audio, language='zh-TW'))
            print(f"你說: {text}")
            return text
        except sr.UnknownValueError: return ""
        except sr.RequestError: return ""

    async def start(self):
        greeting = "你好！我準備好跟你聊天了！" if self.api_key_available else "你好！我現在是鸚鵡模式！"
        print(f"--- 語音引擎已啟動 (模式: {'智慧' if self.api_key_available else '鸚鵡'}) ---")
        await self._trigger_tts(greeting)
        while True:
            user_text = await self.listen_for_voice()
            if user_text:
                if self.api_key_available:
                    await self._process_llm_stream(user_text)
                else:
                    await self._trigger_tts(f"我聽到你說：{user_text}")
            await asyncio.sleep(0.1)

async def main():
    await VoiceEngine(mode="child").start()

if __name__ == "__main__":
    if os.system("command -v ffplay > /dev/null") != 0:
        print("依賴錯誤: 'ffplay' 未安裝。")
    else:
        try: asyncio.run(main())
        except KeyboardInterrupt: print("\n引擎被使用者中斷。")
