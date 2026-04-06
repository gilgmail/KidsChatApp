import SwiftUI

struct ContentView: View {
    @StateObject private var voiceManager = VoiceManager()
    @State private var currentProfile = "kid"

    var body: some View {
        VStack(spacing: 32) {

            // Profile Picker
            Picker("Mode", selection: $currentProfile) {
                Text("Sparky (小孩)").tag("kid")
                Text("Coach (爸爸)").tag("papa")
            }
            .pickerStyle(SegmentedPickerStyle())
            .padding(.horizontal)
            .padding(.top, 48)

            Spacer()

            // AI 回覆
            Group {
                if voiceManager.isLoading {
                    VStack(spacing: 12) {
                        ProgressView()
                            .scaleEffect(1.5)
                        if !voiceManager.recognizedText.isEmpty {
                            Text("「\(voiceManager.recognizedText)」")
                                .font(.callout)
                                .foregroundColor(.secondary)
                                .multilineTextAlignment(.center)
                        }
                    }
                } else {
                    Text(voiceManager.aiReply.isEmpty ? "準備好了，按住按鈕開始說話！" : voiceManager.aiReply)
                        .font(.title2)
                        .multilineTextAlignment(.center)
                        .padding()
                }
            }
            .frame(minHeight: 120)

            // 錄音中：即時顯示辨識文字
            if voiceManager.isRecording {
                Text(voiceManager.recognizedText.isEmpty ? "正在聆聽..." : voiceManager.recognizedText)
                    .foregroundColor(.red)
                    .font(.callout)
                    .padding(.horizontal)
            } else {
                Text(voiceManager.recognizedText)
                    .foregroundColor(.secondary)
                    .font(.callout)
                    .padding(.horizontal)
            }

            Spacer()

            // 按住說話按鈕
            Button(action: {}) {
                ZStack {
                    Circle()
                        .fill(voiceManager.isRecording ? Color.red : Color.blue)
                        .frame(width: 130, height: 130)
                        .shadow(radius: voiceManager.isRecording ? 12 : 4)
                        .animation(.easeInOut(duration: 0.2), value: voiceManager.isRecording)

                    VStack(spacing: 4) {
                        Image(systemName: voiceManager.isRecording ? "waveform" : "mic.fill")
                            .font(.system(size: 32))
                            .foregroundColor(.white)
                        Text(voiceManager.isRecording ? "放開傳送" : "按住說話")
                            .font(.caption)
                            .foregroundColor(.white)
                    }
                }
            }
            .simultaneousGesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { _ in
                        if !voiceManager.isRecording { voiceManager.startRecording() }
                    }
                    .onEnded { _ in
                        Task { await voiceManager.stopRecording(profileId: currentProfile) }
                    }
            )
            .disabled(voiceManager.isLoading)
            .padding(.bottom, 56)
        }
        .onAppear { voiceManager.requestPermissions() }
    }
}

#Preview {
    ContentView()
}
