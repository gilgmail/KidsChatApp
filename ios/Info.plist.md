# Info.plist 必要設定

在 Xcode 的 `Info.plist`（或 Target → Info → Custom iOS Target Properties）加入以下三項。
**缺少任何一項 App 會直接閃退。**

## 必填 Keys

### 1. 麥克風權限
```
Key:   NSMicrophoneUsageDescription
Type:  String
Value: 需要麥克風與 Sparky 說話
```

### 2. 語音辨識權限
```
Key:   NSSpeechRecognitionUsageDescription
Type:  String
Value: 需要語音辨識來理解你說的話
```

### 3. HTTP 允許（Pi5 是區網 HTTP，非 HTTPS）
```
Key:   NSAppTransportSecurity
Type:  Dictionary
  └─  NSAllowsArbitraryLoads
      Type:  Boolean
      Value: YES
```

## Xcode Build Settings

- **Deployment Target**：iOS 16.0+
- **Swift Version**：5.9+

## 在 Info.plist XML 裡的完整寫法

```xml
<key>NSMicrophoneUsageDescription</key>
<string>需要麥克風與 Sparky 說話</string>

<key>NSSpeechRecognitionUsageDescription</key>
<string>需要語音辨識來理解你說的話</string>

<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsArbitraryLoads</key>
    <true/>
</dict>
```
