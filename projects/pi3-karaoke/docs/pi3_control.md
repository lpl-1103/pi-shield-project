# Pi3 Shield 鍵盤控制說明

`pi3_control.py` 已改為**互動式終端機按鍵控制**（不再是網頁版），操作方式參考了你之前的測試檔
`~/it_shield_led_keyboard.py`：程式會把終端機切成 raw 模式，按一下鍵就立刻觸發對應動作，不用按 Enter。

檔案已經上傳到樹莓派：`/home/lpl_1103/pi3_control.py`（用 `RPi.GPIO`，跟舊版一樣，不需要 sudo）。

## 1. 怎麼執行

用一般終端機（不是自動化腳本）SSH 進樹莓派，然後執行：

```bash
ssh lpl_1103@192.168.1.53
python3 ~/pi3_control.py
```

執行後會先印出按鍵說明，接著畫面下方會即時顯示「目前狀態」。

> 必須在真正的互動終端機執行（要有 TTY），不能用背景/非互動方式跑，否則程式會直接印錯誤訊息並結束。

## 2. 按鍵對照表

### 2.1 燈泡（LED1 / LED2）

這片 Shield 的 LED1、LED2 被當成「兩顆燈泡」來控制。**每個按鍵都是直接設定兩顆燈泡的完整狀態**（沒被提到的燈泡會自動關閉），行為單純好記：

| 按鍵 | 動作 |
| --- | --- |
| `1` | 燈泡1 長亮（燈泡2 關閉） |
| `2` | 燈泡2 長亮（燈泡1 關閉） |
| `3` | 燈泡1 + 燈泡2 一起長亮 |
| `4` | 燈泡1 閃爍（燈泡2 關閉） |
| `5` | 燈泡2 閃爍（燈泡1 關閉） |
| `6` | 燈泡1 + 燈泡2 一起閃爍（同步閃） |
| `0` | 兩顆燈泡全部熄滅 |

閃爍間隔預設 0.4 秒，寫死在程式的 `led_blink(..., interval=0.4)` 呼叫裡，要調整就直接改 `pi3_control.py` 裡對應的數字。

沒有做漸變（呼吸燈）效果，照你的要求拿掉了。

### 2.2 蜂鳴器（音符）

| 按鍵 | 音符 |
| --- | --- |
| `q` | Do |
| `w` | Re |
| `e` | Mi |
| `r` | Fa |
| `t` | So |
| `p` | 一鍵播放《粉刷匠》 |

- 每個音符鍵按一次會播放約 0.4 秒。
- **音符頻率（2026-07-16 更新）**：原本表裡用的是低八度頻率（262~523Hz），實測這顆蜂鳴器在這個範圍幾乎聽不出音高差異、都像同一個悶音。換成高八度（`do`=523、`re`=587、`mi`=659、`fa`=698、`so`=784、`la`=880、`xi`=988 Hz）之後音高變化就清楚了，已經在 `pi3_control.py` 的 `NOTE_FREQUENCIES` 裡改好，鍵盤版、LINE 文字指令、網頁面板都會自動套用新頻率，不用各別調整。
- `p` 播放的是你提供的《粉刷匠》簡譜：
  ```
  5353531-24325---5353531-24321---2244325-24325---5353531-24321---
  ```
  數字 1~7 對應 do~xi，`-` 是空一拍（休止）。程式裡的 `PAINTER_SONG_JIANPU` 就是這串數字，改旋律只要改這個字串即可，不用碰下面的產生邏輯。
  每拍長度是 `BEAT_SECONDS`（目前 0.3 秒），要調整播放速度改這個數字就好。
- 播放期間會佔住按鍵輸入（同步播放），放完才能按下一個鍵，這是正常的。

### 2.3 繼電器

| 按鍵 | 動作 |
| --- | --- |
| `o` | 開啟 (ON) |
| `k` | 關閉 (OFF) |

### 2.4 離開

按 `x` 或 `Ctrl+C`：程式會關閉所有燈泡、蜂鳴器、繼電器，並釋放 GPIO，然後結束。

## 3. 跟舊版（網頁版）的差異

- 這次先把網頁前端整個拿掉（照你的要求，先忽略前端），控制方式全部改成終端機按鍵。
- LED 從「LED1~LED5 各自獨立」改成「LED1、LED2 當成兩顆燈泡」，並取消了原本的 `pulse`（漸變）模式，只保留長亮 / 閃爍 / 關閉。
- 蜂鳴器維持用 PWM 產生 do/re/mi/fa/so（跟舊版邏輯一樣），新增了《粉刷匠》一鍵播放。
- 舊的 `/api/led`、`/api/note`、`/api/relay`、`/api/button` 等網頁 API 目前沒有保留在新版程式裡；之後如果要把網頁介面接回來，可以再另外處理。

## 4. 已完成的驗證

- 已在樹莓派上實際跑過一次完整互動測試（透過真實 TTY，逐鍵送出 `1 3 6 q p o k 0 x`），確認：燈泡各種長亮/閃爍組合、Do 音符、《粉刷匠》播放、繼電器開關、離開時 GPIO 正常釋放，全部沒有噴錯誤。
- 因為我看不到 LED 實際發光、也聽不到蜂鳴器聲音，**建議你自己實際按一輪，確認燈泡跟聲音符合預期**，尤其是《粉刷匠》的旋律是否好聽、閃爍速度是否喜歡。

## 5. 之後可以再加的東西（先沒做）

- 按鍵可調整的閃爍速度 / 音符長度
- 讀取 BTN1 / BTN2 實體按鈕狀態
- 把網頁前端接回來，同步新的兩燈泡 + 粉刷匠功能

## 6. LINE 聊天室控制

新增 `line_control.py`：接收 LINE 官方帳號的 Webhook 訊息，指令跟鍵盤版**用同一套字元**（見上面第 2 節的表格），直接在 LINE 聊天室輸入文字就能觸發硬體。指令對照表：

| 傳送文字 | 動作 |
| --- | --- |
| `1` `2` `3` | 燈泡1 / 燈泡2 / 一起 長亮 |
| `4` `5` `6` | 燈泡1 / 燈泡2 / 一起 閃爍 |
| `0` | 全部熄滅 |
| `q` `w` `e` `r` `t` | Do Re Mi Fa So |
| `p` | 播放《粉刷匠》 |
| `o` `k` | 繼電器 開 / 關 |
| `help` | 顯示指令列表 |

### 6.1 架構

```
LINE App --> LINE 官方伺服器 --> (Webhook) --> ngrok tunnel --> 樹莓派 Flask (port 8000) --> GPIO
```

因為樹莓派在區網內、沒有公開 IP，LINE 的 Webhook 需要一個外網可連的 HTTPS 網址，所以用 **ngrok** 開一條通道把樹莓派的 8000 port 曝露出去。用的是你提供的固定網域：

```
https://hurling-narrow-expend.ngrok-free.dev
```

> ⚠️ 這組 ngrok 帳號同時間只能有 1 條 tunnel 在線上。你原本有另一個本機 LLM 專案（launchd 服務 `local.ngrok`，轉發 port 18789）也在搶用同一個網域，設定完成當下已經先幫你 `launchctl unload` 停用。之後如果要重啟那個 LLM 專案的 tunnel，記得先把樹莓派這邊的 ngrok 停掉，不然兩邊會衝突（`ERR_NGROK_334`）。要恢復那個服務可以執行：
> ```bash
> launchctl load ~/Library/LaunchAgents/local.ngrok.plist
> ```

### 6.2 相關檔案

- `~/line_control.py`（樹莓派上）：Flask + Webhook 處理，會 import `pi3_control.py` 裡的 `Pi3Shield` 硬體邏輯。
- `~/pi3_line_config.json`（樹莓派上，`chmod 600`，只有你的帳號能讀）：放 `channel_secret` 跟 `channel_access_token`，不會出現在程式碼裡。**這個檔案不要分享或上傳到任何公開的地方。**

### 6.3 怎麼啟動（每次重開機或斷線後要做）

SSH 進樹莓派後：

```bash
# 1. 啟動控制伺服器（背景執行）
cd ~
nohup python3 line_control.py > line_control.log 2>&1 < /dev/null &
disown

# 2. 啟動 ngrok tunnel（背景執行）
nohup ngrok http --url=https://hurling-narrow-expend.ngrok-free.dev 8000 --log=stdout > ngrok.log 2>&1 < /dev/null &
disown

# 3. 確認狀態
curl -s http://127.0.0.1:4040/api/tunnels   # 應該看到 hurling-narrow-expend.ngrok-free.dev
tail -f ~/line_control.log                  # 看即時 log
```

要停止的話找到對應的 process 用 `pkill -f line_control.py` 跟 `pkill -f "ngrok http"`。

> ngrok 這組免費網域**目前**是固定的（`hurling-narrow-expend.ngrok-free.dev`），只要沒有跟你另一個 LLM 專案搶用，重開機後這個網址理論上不會變，不用每次都去 LINE 後台改 Webhook 網址。

### 6.4 最後一步：LINE Developers Console 設定（只有你能做，我沒有你的帳密登不進去）

1. 登入 [LINE Developers Console](https://developers.line.biz/console/)，找到你自己那個 Messaging API channel（Channel secret 記錄在私人筆記/樹莓派上的 `pi3_line_config.json`，公開版不記錄實際值）。
2. 進「Messaging API」分頁，找到 **Webhook URL**，填入：
   ```
   https://hurling-narrow-expend.ngrok-free.dev/callback
   ```
3. 按 **Verify**，應該會顯示成功（我這邊已經先用假資料實際測過這條路徑，簽章驗證跟 Flask 都正常）。
4. 把 **Use webhook** 打開（Enabled）。
5. 建議把「Auto-reply messages」「Greeting messages」關掉（同一頁或 LINE Official Account Manager 裡），避免官方預設回覆干擾你的指令對話。
6. 用手機 LINE 掃 QR Code 或搜尋 Bot Basic ID 加好友，傳 `help` 測試看看會不會回指令列表。

### 6.5 權限說明

目前**沒有**限制誰能下指令 —— 照你的選擇，任何加這個 LINE 官方帳號好友的人都能控制硬體（開燈、關繼電器等）。如果之後想收回權限，只要在 `line_control.py` 的 `handle_command` 前面加一段檢查 `event['source']['userId']` 是否在白名單內即可，我可以隨時幫你加。

### 6.6 已完成的驗證

- 本地：指令解析（`handle_command`）、LINE 簽章驗證（HMAC-SHA256）、Flask `/callback` 路由（合法簽章 200、錯誤簽章 400）都測過，行為正確。
- 樹莓派：Flask 伺服器啟動正常、ngrok tunnel 建立成功。
- **端對端**：從外網（不是樹莓派本機、也不是區網內）直接打 `https://hurling-narrow-expend.ngrok-free.dev/callback`，送一個簽章正確的模擬 LINE 訊息（文字 `3`），確認：收到 200 OK，且用 `pinctrl get 5` / `pinctrl get 6` 讀到 LED1、LED2 真的變成 `hi`（通電），之後送 `0` 確認變回 `lo`。整條路徑（LINE 格式 → 外網 → ngrok → Flask → GPIO）跑通。
- 因為沒有你的 LINE 帳號，**LINE App 實際傳訊息 → 收到機器人回覆**這段（reply token 那部分）沒辦法由我測試，麻煩你在 Console 設定完 Webhook 後自己測一次。

## 7. 圖形化網頁控制面板（點連結操作，不用打字指令）

`line_control.py` 現在多了一個網頁面板，架構跟 LINE 文字指令共用同一個 `Pi3Shield`、同一個 Flask app，不用另外開伺服器。

### 7.1 怎麼打開

- 網址：`https://hurling-narrow-expend.ngrok-free.dev/panel`
- 在 LINE 聊天室輸入 `面板`、`panel` 或 `help`，機器人會回傳這個連結，點一下就會用 LINE 內建瀏覽器打開。
- **加好友當下**（LINE 的 follow 事件）機器人也會自動傳一次歡迎訊息 + 面板連結，不用先打字才拿得到連結。

### 7.2 畫面內容

首頁是三個分類卡片，點進去才是實際操作按鈕，跟你要求的「選完燈才出現長亮/齊亮/閃爍」一致：

- **💡 燈泡**：長亮（燈泡1 / 燈泡2 / 兩個一起）、閃爍（燈泡1 / 燈泡2 / 兩個一起）、全部熄滅 —— 對應第 2.1 節同一套行為（每個按鈕都是設定兩顆燈泡的完整狀態）。
- **🎵 蜂鳴器**：`1`~`7` 對應 Do Re Mi Fa So La Xi（這是網頁專用的數字對照，跟鍵盤版的字母 `q w e r t` 是分開的兩套，互不影響），加上「🎶 播放《粉刷匠》」按鈕。
- **🔌 其他（繼電器）**：開啟 / 關閉。

按下按鈕後畫面下方會跳出小提示（例如「燈泡1 長亮」），fetch 失敗（樹莓派沒開機/斷線）會顯示「連線失敗，請確認樹莓派是否開機」。

### 7.3 背後的 API（給你參考，面板會自動呼叫，不用手動打）

| 路徑 | 範例 | 說明 |
| --- | --- | --- |
| `/api/led` | `?action=steady1` / `steady2` / `steady_both` / `blink1` / `blink2` / `blink_both` / `off` | 燈泡控制 |
| `/api/note` | `?name=do`（可用 do/re/mi/fa/so/la/xi） | 播放單一音符 |
| `/api/song` | 無參數 | 播放《粉刷匠》（背景執行緒，不會卡住畫面） |
| `/api/relay` | `?action=on` / `off` | 繼電器 |

### 7.4 權限

跟第 6.5 節一樣，面板**沒有**登入或驗證機制，網址只要有人知道（例如聊天室裡看得到）就能直接打開操作。跟你之前選的「不限制」是一致的。

### 7.5 目前的驗證狀況（樹莓派關機中，還沒能實機測）

- 已用 Flask 內建測試工具（不需要真的樹莓派）驗證過：`/panel` 能正常回傳網頁、`/api/led`、`/api/note`、`/api/song`、`/api/relay` 四組 API 在合法/不合法參數下都回傳正確的狀態碼跟 JSON、`follow` 事件會正確觸發歡迎訊息。
- 已經在瀏覽器實際打開這份網頁（手機尺寸 375×812 + 深色模式）確認排版：首頁卡片、燈泡/蜂鳴器/其他三個子頁面、返回鍵，畫面都正常，符合「選分類 → 出現對應操作按鈕」的需求。
- **還沒測的**：連到真正的樹莓派 GPIO（因為你把樹莓派關機了）、LINE App 裡實際點連結打開的體驗。檔案還沒上傳到樹莓派 —— 等你開機後跟我說一聲，我上傳、重啟 `line_control.py`，再做一次端對端測試（跟第 6.6 節一樣的驗證方式：打 API、用 `pinctrl` 確認 GPIO 真的有變化）。
