# Pi Shield Project

用兩台樹莓派做的硬體專案：從終端機按鍵操作，一路做到可以直接在 LINE 聊天室下指令、開圖形化網頁面板、點歌唱歌的完整系統。

## 專案架構

```
樹莓派 3 (ITtraining Pi I/O Shield v3.0)
  └─ pi3_control.py — LED / 蜂鳴器 / 繼電器的核心控制邏輯 + 終端機按鍵互動介面

樹莓派 4 (Raspberry Pi 4 Model B + WM8960 Audio HAT)
  └─ line_control.py — Flask app：
       ├─ LINE Messaging API Webhook（文字指令）
       ├─ 網頁圖形控制面板 (/panel)
       ├─ YouTube 音樂點歌系統 (/karaoke)：排隊、原聲/伴奏切換、
       │    動態同步歌詞、熱門歌曲隨機連播
       └─ /manual 操作手冊頁面
  └─ karaoke.py — 點歌佇列引擎（mpv + yt-dlp 播放、mpv IPC 即時進度查詢、
       lrclib.net 歌詞抓取）
```

兩台樹莓派透過同一個 LINE 官方帳號 + ngrok 固定網域對外串接，實際部署在樹莓派 4 上（樹莓派 3 目前是閒置狀態，之後如果把 IT Shield 接回樹莓派 4，GPIO 排針是相容的）。

## 主要功能

- **LED / 蜂鳴器 / 繼電器控制**（樹莓派 3 + IT Shield）：終端機按鍵、LINE 文字指令、網頁面板三種操作方式共用同一套核心邏輯
- **LINE 聊天室完整控制**：文字指令 + 可點擊的圖形化網頁面板連結
- **YouTube 點歌系統**：多人排隊、原聲/伴奏切換、動態同步歌詞（LRC）、熱門歌曲分類隨機連播（K-pop / 中文流行 / 英文流行）
- **開機自動啟動**：systemd 服務管理，斷電重開機不用手動介入

## 文件

- [`HANDOFF.md`](HANDOFF.md) — 完整開發過程紀錄，按時間順序記錄每個階段做了什麼、踩過哪些坑、為什麼這樣設計
- [`pi3_control.md`](pi3_control.md) — 操作手冊：按鍵對照表、LINE 指令列表、API 說明

## 硬體

- Raspberry Pi 3 Model B + ITtraining Pi I/O Shield v3.0（2 顆 LED、蜂鳴器、繼電器、按鈕）
- Raspberry Pi 4 Model B（8GB）+ Waveshare WM8960 Audio HAT
- 系統：Raspberry Pi OS Lite (Debian Trixie, 64-bit)

## 安全性備註

這個 repo 是公開的，操作紀錄裡的實際密碼、密鑰都已經移除或改成佔位文字，只保留架構跟邏輯本身。樹莓派的 SSH 密碼、LINE Channel Secret/Token、ngrok authtoken 都不會出現在任何檔案裡。
