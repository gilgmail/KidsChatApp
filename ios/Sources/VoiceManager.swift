import Foundation
import Speech
import AVFoundation

class VoiceManager: ObservableObject {
    @Published var recognizedText = ""
    @Published var isRecording = false
    @Published var aiReply = ""
    @Published var isLoading = false

    // 支援中英混講：zh-TW 辨識器可處理中文為主夾雜英文的場景
    private let speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "zh-TW"))
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private let audioEngine = AVAudioEngine()
    private let synthesizer = AVSpeechSynthesizer()

    // Pi5 後端位址，與 .env PORT=8706 一致
    private let apiURL = URL(string: "http://10.1.1.85:8706/talk")!

    // MARK: — 權限申請（App 啟動時呼叫一次）

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

    // MARK: — API 呼叫

    private func callAPI(text: String, profileId: String) async {
        var request = URLRequest(url: apiURL)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 15

        let body: [String: String] = ["profile_id": profileId, "message": text]
        request.httpBody = try? JSONEncoder().encode(body)

        do {
            let (data, _) = try await URLSession.shared.data(for: request)
            if let response = try? JSONDecoder().decode([String: String].self, from: data),
               let reply = response["reply"] {
                DispatchQueue.main.async {
                    self.aiReply = reply
                    self.isLoading = false
                    self.speak(text: reply, profileId: profileId)
                }
            }
        } catch {
            DispatchQueue.main.async {
                self.aiReply = "連線失敗，請確認 Pi5 是否開機 🤖"
                self.isLoading = false
            }
        }
    }

    // MARK: — 本機 TTS 播放

    private func speak(text: String, profileId: String) {
        // 切換到播放模式
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
        try? AVAudioSession.sharedInstance().setActive(true)

        let utterance = AVSpeechUtterance(string: text)
        if profileId == "kid" {
            utterance.voice = AVSpeechSynthesisVoice(language: "zh-TW")
            utterance.rate = 0.45  // 慢速，適合幼兒
        } else {
            utterance.voice = AVSpeechSynthesisVoice(language: "en-US")
            utterance.rate = 0.50
        }

        synthesizer.speak(utterance)
    }
}
