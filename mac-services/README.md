# Mac 端服務

## 為什麼點歌系統需要一台 Mac

樹莓派 4 跑不動本地大模型，所以兩個「聽得懂人話」的能力都放在 Mac 上，
樹莓派透過區網 HTTP 呼叫：

| 能力 | Mac 上的服務 | 埠 | 樹莓派這邊 | 掛掉會怎樣 |
|---|---|---|---|---|
| 自然語言理解 | openclaw gateway → LM Studio (qwen3-8b) | 18789 | `src/nlu.py` | 口語聽不懂，退回「不認識的指令」。**固定格式指令不受影響** |
| 語音轉文字 | mlx-whisper 服務 | 8770 | `src/stt.py` | 語音點歌與麥克風語音控制失效。文字點歌不受影響 |

**兩條都是可降級的**：Mac 關機時點歌系統照常運作，只是變回只認固定指令。
`pi3_line_config.json` 裡的 `nlu_enabled` / `stt_enabled` 可以直接關掉。

## 這個目錄的檔案

| 檔案 | 實際位置 | 說明 |
|---|---|---|
| `whisper_server.py` | `~/.whisper_server/whisper_server.py` | STT 服務本體 |
| `com.lpl.whisper-server.plist` | `~/Library/LaunchAgents/` | 開機自動啟動 STT |
| `com.lpl.bionic-server-start.plist` | `~/Library/LaunchAgents/` | 開機自動啟動 LM Studio server |

openclaw 的設定（`~/.openclaw/openclaw.json`）**沒有收進來**，因為裡面有 gateway token。
需要的設定內容見下面。

## STT：mlx-whisper

模型 `mlx-community/whisper-large-v3-turbo`。三個關鍵設定，都是實測踩出來的：

- `LANGUAGE = 'zh'` — 不鎖語言的話，收音稍差 whisper 就會猜成英文，
  吐出「Every remark remark remark」這種完全無關的內容
- `INITIAL_PROMPT` — 給模型「這段音訊大概會出現什麼詞」的提示（歌名、歌手、指令詞）
- `preprocess_wav()` — 250 Hz 高通濾波 + 正規化，壓掉環境低頻噪音

```bash
launchctl load ~/Library/LaunchAgents/com.lpl.whisper-server.plist
tail -f ~/Library/Logs/whisper-server.log
```

## NLU：openclaw + LM Studio

資料流是**兩層**的，不是樹莓派直接打模型：

```
樹莓派 nlu.py → openclaw gateway (18789) → LM Studio (1234) → qwen3-8b
```

這樣分是因為 openclaw 提供了 agent 層（system prompt、工具權限、路由都在它那邊管），
樹莓派只要送一句話、拿回一行指令。

`~/.openclaw/openclaw.json` 需要的設定：

```json5
{
  models: { providers: { lmstudio: {
    baseUrl: "http://localhost:1234/v1",
    apiKey: "not-needed",
    api: "openai-completions",
    models: [{ id: "qwen/qwen3-8b" }]
  }}},
  agents: {
    defaults: { model: { primary: "lmstudio/qwen/qwen3-8b" } },
    list: [{
      id: "karaoke-nlu",
      name: "小龍蝦",
      model: "lmstudio/qwen/qwen3-8b",
      tools: { profile: "minimal" },      // 沒有檔案/執行/網路權限
      contextInjection: "never"           // system prompt 完全自己控制
    }]
  },
  gateway: {
    bind: "lan",                           // 預設 loopback，樹莓派會連不到
    http: { endpoints: { chatCompletions: { enabled: true } } }
  }
}
```

### 三個踩過的坑

**1. `agents.defaults.model.primary` 沒改，只改 agent 的 `model` 是不夠的。**
症狀是 1.5 秒就回 `upstream provider timeout`——那不是慢，是請求根本被送到早就沒在跑的
ollama。判斷方法：看 openclaw log 裡 `provider=lmstudio` 的次數，是 0 就是這個問題。

**2. qwen3 是 reasoning model，預設會先輸出一大段思考。**
一次翻譯要 27.8 秒。解法是在使用者訊息前面加 `/no_think`，降到 2.8 秒。
`chat_template_kwargs.enable_thinking` 在這條路徑上**沒有作用**，別浪費時間試。

**3. `gateway.bind` 預設是 `loopback`**，要改成 `lan` 樹莓派才連得到。
代價是同區網任何人拿到 token 都能打 gateway 上的**其他** agent（例如有完整檔案
讀寫權限的 `main`）。所以 `karaoke-nlu` 設了 `tools.profile: "minimal"`，
而樹莓派上那份 token 要跟 LINE channel secret 同等看待。

## ⚠ ngrok 網域衝突

Mac 上曾經有一個 `local.ngrok` LaunchAgent，登入時會去搶同一個 ngrok 免費網域。
免費方案**一個網域同時只能有一個持有者**，被搶走之後公開網址會安靜地指向 Mac。

**兩邊都回 HTTP 200，光看狀態碼完全看不出來**，必須比對回傳內容。

已經把那個 plist 改名成 `.disabled` 永久停用。如果哪天公開網址又不對，先查這個。
