import Foundation
import Speech
import AVFoundation

class VoiceManager: ObservableObject {
    @Published var recognizedText = ""
    @Published var isRecording = false
    @Published var aiReply = ""
    @Published var isLoading = false

    private let speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "zh-TW"))
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private let audioEngine = AVAudioEngine()
    private var audioPlayer: AVAudioPlayer?
    private let synthesizer = AVSpeechSynthesizer()  // 必須是 stored property，否則會提早釋放

    private let apiURL = URL(string: "http://10.1.1.85:8706/talk")!

    // MARK: — 權限申請

    func requestPermissions() {
        SFSpeechRecognizer.requestAuthorization { _ in }
        AVAudioSession.sharedInstance().requestRecordPermission { _ in }
    }

    // MARK: — 開始錄音（STT）

    func startRecording() {
        guard !isRecording else { return }
        recognizedText = ""

        let audioSession = AVAudioSession.sharedInstance()
        try? audioSession.setCategory(.record, mode: .measurement, options: .duckOthers)
        try? audioSession.setActive(true, options: .notifyOthersOnDeactivation)

        recognitionRequest = SFSpeechAudioBufferRecognitionRequest()
        guard let request = recognitionRequest else { return }
        request.shouldReportPartialResults = true

        let inputNode = audioEngine.inputNode
        recognitionTask = speechRecognizer?.recognitionTask(with: request) { [weak self] result, _ in
            if let result = result {
                DispatchQueue.main.async {
                    self?.recognizedText = result.bestTranscription.formattedString
                }
            }
        }

        let format = inputNode.outputFormat(forBus: 0)
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            self?.recognitionRequest?.append(buffer)
        }

        audioEngine.prepare()
        try? audioEngine.start()
        DispatchQueue.main.async { self.isRecording = true }
    }

    // MARK: — 停止錄音，送出至 Pi5

    func stopRecording(profileId: String) async {
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        recognitionRequest?.endAudio()
        recognitionTask?.cancel()

        DispatchQueue.main.async {
            self.isRecording = false
            self.isLoading = true
        }

        guard !recognizedText.isEmpty else {
            DispatchQueue.main.async { self.isLoading = false }
            return
        }

        await callAPI(text: recognizedText, profileId: profileId)
    }

    // MARK: — API 呼叫（文字 + 音訊一次取回）

    private func callAPI(text: String, profileId: String) async {
        var request = URLRequest(url: apiURL)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 30  // TTS 需要更長時間

        let body: [String: String] = ["profile_id": profileId, "message": text]
        request.httpBody = try? JSONEncoder().encode(body)

        do {
            let (data, _) = try await URLSession.shared.data(for: request)

            struct TalkResponse: Decodable {
                let reply: String
                let audio_b64: String?
            }

            guard let response = try? JSONDecoder().decode(TalkResponse.self, from: data) else {
                // 解析失敗時顯示原始錯誤（例如 429 quota 訊息）
                let raw = String(data: data, encoding: .utf8) ?? "未知錯誤"
                DispatchQueue.main.async {
                    self.aiReply = raw.contains("429") ? "API 用量已滿，請稍後再試" :
                                   raw.contains("detail") ? "伺服器錯誤，請稍後再試" : "回應格式錯誤"
                    self.isLoading = false
                }
                return
            }

            DispatchQueue.main.async { self.aiReply = response.reply }

            // 優先播放 Gemini 語音，fallback 到系統 TTS
            if let audioB64 = response.audio_b64,
               let audioData = Data(base64Encoded: audioB64) {
                playAudio(data: audioData)
            } else {
                DispatchQueue.main.async {
                    self.isLoading = false
                    self.fallbackSpeak(text: response.reply, profileId: profileId)
                }
            }

        } catch {
            DispatchQueue.main.async {
                self.aiReply = "連線失敗，請確認 Pi5 是否開機"
                self.isLoading = false
            }
        }
    }

    // MARK: — 播放 WAV 音訊

    private func playAudio(data: Data) {
        DispatchQueue.main.async {
            self.isLoading = false
            do {
                try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
                try AVAudioSession.sharedInstance().setActive(true)
                self.audioPlayer = try AVAudioPlayer(data: data)
                self.audioPlayer?.play()
            } catch {
                // 若播放失敗靜默降級
            }
        }
    }

    // MARK: — 備用系統 TTS

    private func fallbackSpeak(text: String, profileId: String) {
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: profileId == "kid" ? "zh-TW" : "en-US")
        utterance.rate = 0.45
        synthesizer.speak(utterance)
    }
}
