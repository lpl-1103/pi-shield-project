# 交接文件 — Pi3 Shield 控制專案

最後更新：2026-07-16（收工時樹莓派已關機，所有服務目前**沒有**在跑）

## 我們在做什麼

把樹莓派上的 ITtraining Pi I/O Shield v3.0（2 顆燈泡 LED1/LED2、1 個蜂鳴器、1 個繼電器）做成可以簡單操作的專案，操作方式從「終端機按鍵」一路擴充到「LINE 聊天室文字指令」再到「LINE 裡點連結打開的圖形化網頁面板」。

樹莓派資訊：
- SSH: `ssh lpl_1103@192.168.1.53`，密碼見私人筆記（公開版不記錄實際密碼）（使用者名稱是 `lpl_1103`，主機名稱是 `LPL`，不要搞混）
- 硬體：Raspberry Pi 3 Model B，OS 是 Debian Trixie (13) aarch64

## 已經完成什麼

1. **[pi3_control.py](../src/pi3_control.py)**（本地 + 已上傳到樹莓派 `~/pi3_control.py`）
   核心 `Pi3Shield` 類別（LED 長亮/閃爍/關、蜂鳴器 PWM 音符+旋律播放、繼電器開關），以及一個獨立可跑的終端機按鍵互動介面（raw tty 模式，仿照樹莓派上原本的 `~/it_shield_led_keyboard.py`）。
   - LED：`1`/`2`/`3` 長亮（單1/單2/一起），`4`/`5`/`6` 閃爍（單1/單2/一起），`0` 全關。每個指令都是設定「兩顆燈泡的完整狀態」，沒提到的燈泡會自動關閉。
   - 蜂鳴器：`q w e r t` = do re mi fa so，`p` = 播放《粉刷匠》（旋律用使用者提供的簡譜 `PAINTER_SONG_JIANPU` 生成，可直接改那個字串調旋律）。
   - 繼電器：`o` 開 `k` 關。
   - 已拿掉原本的「漸變/pulse」LED 模式（照需求砍掉）。

2. **[line_control.py](../src/line_control.py)**（本地 + 已上傳到樹莓派 `~/line_control.py`）
   Flask app，兩種操作介面：
   - **LINE 文字指令**：`/callback` 路由接收 LINE Webhook，驗證 `X-Line-Signature`（HMAC-SHA256），指令跟鍵盤版共用同一套字元。加好友（follow 事件）會自動回傳歡迎訊息+面板連結；傳 `面板`/`panel`/`help` 也會拿到連結。
   - **網頁圖形面板**：`/panel` 路由回傳一個手機優先的單頁 HTML（首頁 3 個分類卡片：💡燈泡 / 🎵蜂鳴器 / 🔌其他，點進去才出現對應按鈕）。背後呼叫 `/api/led`、`/api/note`、`/api/song`、`/api/relay` 四組 JSON API。網頁的蜂鳴器按鈕是 `1`~`7` 對應 do~xi（跟鍵盤版的字母鍵是分開的兩套對照，互不影響）。
   - 兩種介面共用同一個全域 `shield = Pi3Shield(...)` 實例，所以只需要跑一個 Flask process。

3. **LINE 串接**
   - 使用者提供的 Channel secret / Channel access token 存在樹莓派上的 `~/pi3_line_config.json`（`chmod 600`），**沒有**寫死在程式碼裡，也沒有留在本地 Mac 或提交到任何地方。
   - 用 ngrok 把樹莓派的 8000 port 曝露到外網，固定網域：`https://hurling-narrow-expend.ngrok-free.dev`。
   - 使用者已經自己在 LINE Developers Console 把 Webhook URL 設成 `https://hurling-narrow-expend.ngrok-free.dev/callback` 並開啟 Use webhook，Verify 過、實際用手機 LINE 測試過文字指令，確認可用。

4. **蜂鳴器音調修正**：原本 `NOTE_FREQUENCIES` 用低八度（262~523Hz），實測這顆蜂鳴器在這個範圍幾乎聽不出音高差異（一度懷疑是主動式蜂鳴器，做了 on/off vs 變頻的 A/B 測試排除這個可能）。換成使用者提供的高八度頻率（do=523 re=587 mi=659 fa=698 so=784 la=880 xi=988，Hz）後，使用者實際聽過確認音高變化正常。這個表是三種介面共用的，已經一次修好。

5. **全程都在真實硬體上驗證過**，不是只測邏輯：
   - 用 `pinctrl get <pin>` 直接讀 GPIO 電位（`hi`/`lo`）確認長亮/閃爍/繼電器真的動作，不是只看程式回傳成功。
   - 從外網（不是樹莓派本機、也不是區網內）直接打 ngrok 公開網址，送簽章正確的模擬 LINE 訊息，驗證整條路徑：LINE 格式 → 外網 → ngrok → Flask → GPIO。
   - 網頁面板在瀏覽器裡用手機尺寸(375×812) + 深色模式實際點過一輪確認排版。

## 當前卡在哪 / 還沒做完的

- **樹莓派已關機，兩個服務目前都沒在跑**（Flask `line_control.py` + ngrok tunnel）。下次要用之前必須手動重啟，見下面「下一步」。
- **沒有設開機自動啟動**：目前是手動 `nohup ... & disown` 起服務，樹莓派重開機或斷電不會自動恢復。如果要長期穩定用，需要另外設 systemd user service 或 `crontab @reboot`（還沒做）。
- **使用者還沒在手機 LINE 裡實際點過面板連結**做完整體驗測試——文字指令跟網頁 API/GPIO 都個別驗證過，但「LINE App 內建瀏覽器打開面板、手指點按鈕」這個最終使用者體驗流程還沒有使用者自己確認過。
- **沒有任何存取限制**：LINE 機器人跟網頁面板目前任何加好友/拿到連結的人都能操作硬體。這是使用者明確選擇的（優先求簡單），但要記得這是已知、刻意的決定，不是遺漏。
- BTN1 / BTN2 實體按鈕讀取沒有實作（一直是刻意先跳過的範圍外項目）。

## 下一步計畫（建議順序）

1. 開機樹莓派，SSH 進去，照下面「重啟服務」的指令把 `line_control.py` 跟 ngrok 兩個服務啟動起來。
2. 用手機 LINE 實際點一次面板連結，走一輪所有按鈕，確認跟預期一致。
3. 問使用者要不要設開機自動啟動（systemd/cron），如果要長期用建議設一下，不然每次重開機都要手動來一次。
4. 問使用者要不要加存取限制（白名單 LINE userId），如果要，改 `line_control.py` 的 `handle_command` 前面加一段檢查即可。
5. 其餘功能（BTN1/BTN2 讀取等）看使用者需求再排。

### 重啟服務指令（樹莓派開機、SSH 進去之後）

```bash
cd ~
nohup python3 line_control.py > line_control.log 2>&1 < /dev/null &
disown
nohup ngrok http --url=https://hurling-narrow-expend.ngrok-free.dev 8000 --log=stdout > ngrok.log 2>&1 < /dev/null &
disown
sleep 3
curl -s http://127.0.0.1:4040/api/tunnels   # 確認 tunnel 是 hurling-narrow-expend.ngrok-free.dev
curl -s -o /dev/null -w "HTTP:%{http_code}\n" http://127.0.0.1:8000/
```

Webhook URL 理論上**不需要**重新去 LINE 後台設定（固定網域），除非 ngrok 那組帳號的網域又被搶走（見下面的坑）。

## 踩過的坑，絕對不要再踩

1. **SSH 使用者名稱是 `lpl_1103`，不是 `LPL`**。`LPL` 是主機名稱（shell prompt 顯示 `lpl_1103@LPL`），一開始容易搞混，用 `LPL` 當帳號登入會失敗。

2. **ngrok 免費帳號同時間只能有 1 條 tunnel**。使用者的 Mac 上有另一個 launchd 背景服務 `local.ngrok`（設定檔 `~/Library/LaunchAgents/local.ngrok.plist`，`KeepAlive: true`，轉發本機 port 18789，是給以後的 LLM 專案用的）會自動搶用同一個 ngrok 網域，導致樹莓派這邊開 tunnel 一直報 `ERR_NGROK_334 endpoint already online`。**已經 `launchctl unload` 停用**，設定檔還在、沒刪。
   - 之後如果樹莓派這邊要用 ngrok，先確認 Mac 那個服務沒被重新載入。
   - 如果以後真的要同時跑兩個 tunnel，得升級 ngrok 付費方案，或其中一邊改用別的穿透方式（如 Cloudflare Tunnel）。
   - 要恢復 Mac 那個 LLM 專案的 tunnel：`launchctl load ~/Library/LaunchAgents/local.ngrok.plist`。

3. **`nohup cmd & disown` 之後緊接著 `cat log` 常常是空的** —— 不是啟動失敗，是 Python 寫到檔案的 stdout 有 buffering，需要 `sleep 2` 左右再檢查一次 log 或直接用 `curl` 打 port 確認活著，不要看到空 log 就以為啟動失敗。

4. **改了 `pi3_control.py` 或 `line_control.py` 之後，一定要 `pkill -f "python3 line_control.py"` 再重啟**，Python 不會自動重載程式碼；改完沒重啟會一直測到舊版行為，白白 debug 半天。

5. **蜂鳴器頻率不是隨便選的**：低八度（262~523Hz）在這顆蜂鳴器上幾乎聽不出音高差異，會誤以為是主動式蜂鳴器或接線問題。已確認正確頻率是高八度 523~988Hz（`NOTE_FREQUENCIES` 已修好），以後如果又「聽起來都同一個調」，先懷疑頻率範圍，不要急著懷疑硬體或 PWM 邏輯。

6. **bash/zsh 裡帶 `?` 的網址一定要加引號**，例如 `curl "https://xxx/api/led?action=on"`，不加引號 zsh 會把 `?` 當 glob pattern 直接報 `no matches found`，很容易誤判成 API 真的壞了。

7. **不要把 `pi3_line_config.json`（LINE 的 channel_secret / access token）或 ngrok authtoken 留在本地 Mac 專案資料夾裡**——目前這些密鑰只放在樹莓派上（`chmod 600`），本地測試用的都是假值，測完就刪了。以後要測 LINE 相關功能，記得比照辦理，不要把真密鑰留在容易被同步/分享的地方。

8. **這台 Mac 的 Bash 工具是操作真實系統**（不是沙盒），`launchctl`、`ifconfig` 等指令都是真的動到使用者本機環境，改動前（尤其是 unload 服務這種）務必先跟使用者確認，不要自己直接動。

## 相關檔案位置

本地 Mac（`/Users/lpl/Hardware Development/`）：
- `pi3_control.py` — 核心硬體邏輯 + 鍵盤介面
- `line_control.py` — LINE Webhook + 網頁面板
- `pi3_control.md` — 給使用者看的操作說明文件（按鍵對照、API、LINE設定步驟都在這）
- `pi3_basic/` — 廠商原廠 C 語言範例與 `it_shield.h`（腳位定義的原始出處）
- `HANDOFF.md` — 本文件

樹莓派（`/home/lpl_1103/`）：
- `pi3_control.py`、`line_control.py` — 跟本地同步的版本
- `pi3_line_config.json`（`chmod 600`）— LINE 密鑰，不要外流
- `it_shield_led_keyboard.py`、`board_led_keyboard.py` — 使用者原本的測試腳本（設計參考來源，沒有動過）

## 有問題找不到方向時

先看 [pi3_control.md](pi3_control.md) 的操作說明（按鍵/API/LINE設定都寫在那），這份 HANDOFF.md 是給「接手的人/下一次會話」快速搞懂狀態用的，細節操作文件優先看 `pi3_control.md`。

---

# 2026-07-17 更新：新增樹莓派 4，LINE 機器人搬家 + 點歌系統

⚠️ **重要**：上面所有內容是昨天（2026-07-16）針對**樹莓派 3**（IT Shield，192.168.1.53）寫的，今天沒有改動那些內容，但架構上已經有變化：**LINE 機器人現在跑在新的樹莓派 4 上，不是樹莓派 3**。樹莓派 3 目前處於「沒在跑 LINE 服務」的閒置狀態（ngrok tunnel 已經移到樹莓派 4）。

## 今天在做什麼

使用者拿到一台新的、封裝好機殼的樹莓派 4（原本只知道有兩個顯示器接口跟一個音源孔，不知道詳細規格），請我：
1. 檢查一張使用者手上的 32G SD 卡有沒有資料，沒有就燒錄新的 Raspberry Pi OS
2. 把樹莓派 3 上做的東西盡量搬到樹莓派 4（尤其是 LINE 連結），GPIO 相關（LED/蜂鳴器/繼電器）先擱置，因為新機器沒接 IT Shield
3. 幫忙查出這台機器實際的硬體規格
4. 後續追加：LINE 控制播放 YouTube 音樂、把點歌系統做成完整的 KTV 風格前端（排隊、歌詞同步、原聲/伴奏切換）

## 新樹莓派 4 資訊

- SSH: `ssh lpl1103@192.168.1.111`，密碼見私人筆記（公開版不記錄實際密碼）（**注意帳號是 `lpl1103`，沒有底線 `_`**——跟樹莓派 3 的 `lpl_1103` 不一樣，是因為 Raspberry Pi OS 的 userconf 機制不接受帳號名稱有底線）
- 型號：**Raspberry Pi 4 Model B Rev 1.4**，8GB 記憶體版本，透過 `/proc/device-tree/model` 確認過，不是用外觀猜的
- OS：跟樹莓派 3 一樣是全新燒錄的 Raspberry Pi OS Lite (Debian Trixie, 64-bit)
- 這台 sudo **不是** NOPASSWD（跟樹莓派 3 不同），下指令要用 `ssh -t` 並準備好回應 `[sudo] password for lpl1103:` 提示，密碼同上
- WiFi：SSID `Golden-IC`，已經設定好開機自動連線（WiFi 密碼跟國碼設定寫在 `/etc/NetworkManager/system-connections/preconfigured.nmconnection`，國碼用 `raspi-config nonint do_wifi_country TW` 設的，密碼見私人筆記）

## 已經完成什麼

1. **SD 卡處理**：原本那張 32G 卡裡面是 2021 年的舊 Raspbian Buster（幾乎沒真實資料，只是開機測試過一次），已經確認過、徵得同意後重新燒錄成最新 Raspberry Pi OS Lite (Trixie)。燒錄方式是本地 Mac 下載 `.img.xz` → 解壓縮同時透過 SSH 串流直接 `dd` 進樹莓派 3 讀卡機裡的卡（因為樹莓派 3 自己的系統碟空間只剩 373MB，不夠放，用這個方法完全不佔用樹莓派的硬碟空間）。燒錄完手動掛載開機分割區寫入 `ssh`（開機檔）+ `userconf.txt`（帳號密碼）+ WiFi 設定檔，才把卡片實際插到樹莓派 4 上開機。

2. **硬體規格確認**：一開始不知道這台的規格，用 `/proc/device-tree/model` + `aplay -l`（看到 `Headphones`、`vc4hdmi0`、`vc4hdmi1` 三張音效卡）確認是標準 Pi 4 Model B。接著發現 I2C 匯流排上有顆晶片在位址 `0x1a`（用 `i2cdetect -y 1` 掃出來的），上網查證是 **WM8960 音效解碼晶片**的標準位址，對應到 **Waveshare WM8960 Audio HAT**（一片透過 40-pin GPIO 疊上去的音效擴充板），裝了官方驅動（`github.com/waveshareteam/WM8960-Audio-HAT`，dkms 編譯核心模組）確認變成可用的 ALSA 音效卡。

3. **音效輸出的重要發現**：這台實際的耳機是接在 **Pi 4 自己內建的耳機孔**（`hw:1,0`，card 1 `bcm2835 Headphones`），**不是**接在 WM8960 那片板子上（`hw:0,0`）。這兩個是完全獨立的音效裝置，一開始播放沒聲音就是因為程式對著 WM8960 播、耳機卻插在別的地方。用 `speaker-test -tsine` 分別測兩張卡才抓出來的。**以後如果又遇到「有播放但沒聲音」，先確認耳機/喇叭實際插在哪張卡，不要預設是 WM8960。**

4. **YouTube 音樂播放**（[line_control.py](../src/line_control.py) + [karaoke.py](../src/karaoke.py)）：裝了 `mpv`、`yt-dlp`（升級成 GitHub 最新 standalone 版，蓋掉太舊的 apt 版本）、`deno`（yt-dlp 做 YouTube 簽章解析需要的 JS runtime，沒裝的話很容易解析失敗）。

5. **LINE 機器人搬家到樹莓派 4**：`pi3_line_config.json`（LINE 密鑰）直接用對話裡使用者早先提供的原始值重建到樹莓派 4 上（樹莓派 3 當時已關機拿不到），ngrok 也裝在樹莓派 4 上、用同一組 authtoken + 同一個固定網域 `hurling-narrow-expend.ngrok-free.dev`。**LINE Developers Console 的 Webhook URL 完全沒有變動過**，因為網域沒變，後端悄悄換成樹莓派 4 而已。

6. **點歌系統（KTV 風格，今天最大的功能）**：
   - **後端**：新檔案 `karaoke.py`，維護一份排隊清單 + 背景執行緒播放迴圈，用 mpv 的 `--input-ipc-server` 開一個 unix socket，即時查詢播放進度（`time-pos`/`duration`），歌詞用 `lrclib.net`（免費公開歌詞資料庫，不用金鑰）搜尋 LRC 逐行時間軸格式並解析。
   - **前端**：`/karaoke`（KTV 風格：現正播放卡片+進度條、動態同步歌詞、點歌輸入框含原聲/伴奏切換、排隊列表含頂歌/刪除按鈕，每 1.5 秒輪詢更新）、`/manual`（操作手冊頁面）。
   - **LINE 指令**：`點歌 <歌名>`（尾綴 `0` 表示要伴奏版，例如「點歌 小星星0」會去搜「小星星 伴奏 instrumental」）、`排隊`/`查詢`/`歌單`（列出目前播放+排隊，含編號）、`切歌`、`刪除 <編號>`、`頂歌 <編號>`、`原聲`/`伴奏`（切換目前播放版本，會重新搜尋播放，沒辦法接續原本位置）、`停止`（清空排隊+停止）。喚醒詞 `小樂小樂，我要點歌` 會回傳點歌頁面+操作手冊連結。
   - 點歌會記錄「誰點的」，透過 LINE Messaging API 的 Get Profile 拿 `displayName`（拿不到會顯示「匿名」，不會報錯）。

7. **一個實測修正**：歌詞搜尋一開始用 YouTube 解析出來的影片標題去查（例如「小星星-兒歌小星星-星天樂園-...-Stars Kingdom」這種很長很雜的標題），常常查不到。改成優先用使用者點歌時輸入的乾淨關鍵字（例如「小星星」）去查，查不到才拿雜亂標題當備援，修完歌詞才抓得到。

8. **全部端對端測試過**：多人排隊（不同 LINE userId 分別點歌）、伴奏版搜尋（真的搜到「粉刷匠 (伴奏版)」的影片）、切歌、原聲/伴奏即時切換、歌詞同步抓取、mpv IPC 播放進度查詢，都是從外網打真實簽章的 LINE webhook 測試，不是只測程式邏輯。網頁也在瀏覽器實際點過確認排版跟互動（模式切換按鈕的選中樣式等）。

## 當前卡在哪 / 還沒做完的

- **樹莓派 3 現在閒置**：ngrok/LINE 服務都搬到樹莓派 4 了，樹莓派 3 上的 `pi3_control.py`/`line_control.py` 還在，但沒有 tunnel 指過去，等於斷線狀態。如果以後要恢復樹莓派 3 的 IT Shield 功能（LED/蜂鳴器/繼電器），要嘛接回樹莓派 4（GPIO 排針相容）要嘛想辦法讓兩台都能對外（ngrok 免費版一次只能一條 tunnel，見昨天的坑）。
- **樹莓派 4 沒有設開機自動啟動**：跟樹莓派 3 昨天的狀況一樣，`line_control.py`（含 karaoke 播放引擎）+ ngrok 都是手動 `nohup ... & disown` 起的，重開機/斷電不會自動恢復。
- **音樂只能在樹莓派本機喇叭放**：不是傳到使用者手機播放，這是設計上就這樣（樹莓派接了實體耳機/喇叭）。
- **原聲/伴奏切換的已知限制**：技術上是重新搜尋播放另一個版本，不是即時人聲分離（使用者已經確認接受這個做法，AI 人聲分離在沒有 GPU 的 Pi 4 上跑一首歌要好幾分鐘，不適合即時切換）。
- **歌詞不保證找得到**：`lrclib.net` 是社群資料庫，冷門歌或找不到同步歌詞的歌會顯示「沒有找到歌詞」。
- **一樣沒有存取限制**：跟昨天的決定一致，LINE 上任何人、網頁連結任何人拿到都能操作點歌/排隊。

## 新增的坑，不要再踩

9. **這台 sudo 需要密碼**（樹莓派 3 是 NOPASSWD，這台不是）。用 `ssh host "sudo xxx"` 直接下指令會卡在 `sudo: a terminal is required to read the password`，一定要用 `ssh -t host "sudo xxx"` 並在 expect 腳本裡準備好回應密碼提示（同時處理 SSH 登入密碼跟 sudo 密碼兩個提示，兩個提示文字都含 `password`，用同一個 `expect { "password" { send ... ; exp_continue } eof }` 迴圈就能兩個一起處理，不用分開寫）。

10. **不要把 `dd` 燒錄指令的目標裝置搞錯**。燒錄前一定要反覆用 `lsblk`/`fdisk -l` 確認目標裝置的實際容量、分割表、掛載狀態，燒到樹莓派自己的開機碟（`mmcblk0`）而不是外接讀卡機的卡（`sda`）會直接毀掉正在跑的系統。這次是先讀取確認、跟使用者明確核對容量兜不攏的地方（使用者說 32G，第一次讀到的其實是接錯卡的 59.5G HassOS 卡）才動手，任何「這是不是我要燒的那張卡」的疑慮都要先確認再執行。

11. **`lsblk` 的資訊在使用者換卡之後可能是舊的快取**，尤其是 USB 讀卡機熱插拔卡片時。要看到正確的當下狀態，用 `sudo partprobe <device>` 或 `sudo blockdev --rereadpt <device>` 強制重新掃描分割表，再搭配 `sudo fdisk -l <device>`（會直接讀裝置本身，比 `lsblk` 可靠）核對。

12. **ngrok 免費帳號的網域可能被別的裝置/服務搶佔，而且不一定是「殘留」**，可能是真的有別的地方正在用。判斷方式：`ngrok.log` 裡如果重試多次都是同一個 `ERR_NGROK_334`，且本機 `ps aux | grep ngrok` 查不到任何 process，就代表是別的裝置在用，要去 [ngrok Dashboard](https://dashboard.ngrok.com/endpoints) 看 Agent 詳細資訊（會顯示 OS、啟動時間、啟動帳號）確認來源，不要自己亂猜亂殺。

13. **yt-dlp 的 apt 版本容易太舊、YouTube 常改版讓舊版解析失效**，遇到「no supported JavaScript runtime」或解析失敗，先裝 `deno`（`curl -fsSL https://deno.land/install.sh | sh`，記得額外 `ln -sf` 連結到 `/usr/local/bin` 讓非互動 SSH session 也找得到，因為 `~/.bashrc` 對非互動 shell 不會生效）並把 yt-dlp 換成 GitHub release 的最新 standalone 版本（放 `/usr/local/bin/yt-dlp`，會蓋掉 apt 版本，因為 PATH 順序在前面）。

14. **mpv 不支援直接吃 `ytsearch1:` 這種 yt-dlp 搜尋語法**（會被當成本地檔案路徑，報「No such file or directory」）。要先用 `yt-dlp --print "%(title)s" --print "%(id)s" "ytsearch1:關鍵字"` 解析出實際的 `https://www.youtube.com/watch?v=<id>` 網址，再把這個真正的網址交給 mpv 播放。

15. **mpv 的 IPC socket（`--input-ipc-server`）查詢播放位置，歌曲剛開始播放的頭幾秒可能還沒有資料**（`time-pos`/`duration` 回傳 `null` 很正常），不是查詢邏輯有問題，多等幾秒或讓前端輪詢自然補上就好，不用特別處理成錯誤。

## 相關檔案位置（新增）

本地 Mac（`/Users/lpl/Hardware Development/`）：
- `karaoke.py` — 點歌佇列引擎（今天新增）
- `line_control.py` — 已擴充：YouTube 播放 + 點歌系統路由/指令（原本 Pi3 Shield 的部分沒有變動，兩邊功能都在同一份檔案裡）

樹莓派 4（`/home/lpl1103/`）：
- `pi3_control.py`、`line_control.py`、`karaoke.py`、`pi3_line_config.json`（`chmod 600`）— 跟本地同步
- `WM8960-Audio-HAT/`（git clone 下來的官方驅動原始碼，裝完可以留著也可以刪，不影響已安裝的驅動）

## 重啟服務指令（樹莓派 4，開機、SSH 進去之後）

```bash
cd ~
nohup python3 line_control.py > line_control.log 2>&1 < /dev/null &
disown
nohup ngrok http --url=https://hurling-narrow-expend.ngrok-free.dev 8000 --log=stdout > ngrok.log 2>&1 < /dev/null &
disown
sleep 3
curl -s http://127.0.0.1:4040/api/tunnels
curl -s -o /dev/null -w "HTTP:%{http_code}\n" http://127.0.0.1:8000/karaoke
```

改完程式碼一樣要 `pkill -f "python3 line_control.py"`（順便 `pkill -f mpv` 清掉可能還在播的音樂）再重啟，Python 不會自動重載。

---

# 2026-07-20 更新：樹莓派 4 設定開機自動啟動

之前一直是「已知還沒做完的事」清單裡的一項，今天補上了。

## 做了什麼

用 systemd 服務取代手動 `nohup ... & disown`：
- `/etc/systemd/system/line-control.service` — 跑 `python3 /home/lpl1103/line_control.py`，`User=lpl1103`，`Restart=on-failure`
- `/etc/systemd/system/ngrok-tunnel.service` — 跑 ngrok tunnel，`After=` 依賴 `line-control.service`（確保 Flask 先起來 ngrok 才連過去），一樣 `Restart=on-failure`

兩個都 `After=network-online.target` + `Wants=network-online.target`，確保 WiFi 連上之後才啟動，不會因為網路還沒好而失敗。

用 `sudo systemctl enable line-control.service ngrok-tunnel.service` 設成開機啟動。

## 驗證方式

不是只有 `enable` 就相信它會動，是**真的下 `sudo reboot` 重開機一次**，開機後完全沒手動下任何指令，直接檢查：
- `sudo systemctl is-active line-control.service ngrok-tunnel.service` → 兩個都是 `active`
- 從外網打 `https://hurling-narrow-expend.ngrok-free.dev/karaoke` 跟 `/manual` → 都是 200

確認整條路徑（開機 → WiFi 連線 → systemd 啟動 Flask → systemd 啟動 ngrok → 外網打得通）自動化沒問題。

## 以後要注意

- **改 `line_control.py`/`karaoke.py` 之後**，重啟方式從 `pkill + nohup` 改成 `sudo systemctl restart line-control.service`（改動 Flask app 不需要動 ngrok，不用重啟 `ngrok-tunnel.service`）。
- 要看 log 用 `sudo journalctl -u line-control.service -f`（或 `-u ngrok-tunnel.service`），不再是看 `~/line_control.log` 這個檔案了（systemd 會接管 stdout/stderr 到 journal，`~/line_control.log` 這個舊檔案不會再更新）。
- 要臨時停用開機自動啟動：`sudo systemctl disable line-control.service ngrok-tunnel.service`（設定還在，只是開機不會自動跑，跟樹莓派 3 那邊「刻意先不設」的狀態不同，這裡是要停用才需要動作）。

---

# 專案發布到 GitHub

專案已經公開發布：**https://github.com/lpl-1103/pi-shield-project**

發布前把文件裡明碼寫的密碼／密鑰都清掉了（SSH/sudo 密碼、LINE Channel Secret），`.gitignore` 排除了 `pi3_line_config.json`、Claude Code 工具設定檔（`.claude/`、`.embedder/`）跟一個編譯過的執行檔。README.md 是新增的專案首頁介紹。

**換電腦要接著開發的話**：`git clone https://github.com/lpl-1103/pi-shield-project.git`，改完照平常 `git add / commit / push`，跟在哪台機器上操作完全無關。第一次在新機器上 push 前要重新登入一次 GitHub。

---

# ALSA 音效卡編號不穩定，造成「重開機後沒聲音」的 bug 修復

## 問題

今天重啟服務之後，樹莓派 4 完全沒聲音，`mpv` process 有在跑、API 狀態也顯示正常在播放，但實際上聽不到任何聲音。

## 根本原因

`karaoke.py` 原本把音效輸出裝置寫死成 `AUDIO_DEVICE = 'alsa/hw:1,0'`（在 2026-07-17 那次修好音效問題時，`hw:1,0` 剛好對應到 Pi 4 內建耳機孔 `bcm2835 Headphones`）。但**這台機器的 ALSA 卡編號在每次開機時不保證固定**——`wm8960soundcard` 跟 `bcm2835 Headphones` 誰是 card 0、誰是 card 1 會隨機互換（實測：某次重開機後互換了一次，再重開一次又換回來）。一旦編號跟寫死的 `hw:1,0` 對不上，程式就會忠實地把音樂播到 WM8960 那片沒接喇叭的板子上，`mpv` 完全正常運作、不會報任何錯誤，只是聲音出到了沒人接收的地方。

**這是個很難靠看 log 抓到的 bug**——因為所有東西（process 存活、API 狀態、mpv 沒有錯誤訊息）看起來都完全正常，只有「人耳朵聽不到」這個症狀。以後遇到「日誌都正常但沒聲音」，第一個該懷疑的就是音效卡編號是不是變了，用 `cat /proc/asound/cards` 立刻能確認。

## 修法

1. 新增 `_detect_headphone_card()`：程式啟動時讀取 `/proc/asound/cards`，用**名稱**（找含有 `"Headphones"` 字樣的那一行）動態判斷正確的卡號，不再寫死數字。`AUDIO_DEVICE` 從固定字串改成根據偵測結果組出來。
2. 順便發現音量設定也有類似的持久化問題：之前用 `amixer` 調過的音量（-10dB），本來想用 `sudo alsactl store` 存起來，但這台機器上 WM8960 的開機腳本（`wm8960-soundcard.service`）**每次開機都會刪除並重建 `/var/lib/alsa/asound.state`**，把 `alsactl store` 存的東西蓋掉。改成不依賴系統層存檔機制，程式自己在 `karaoke.start()` 時主動下 `amixer` 指令設定音量（`_apply_default_volume()`），每次啟動都自己設一次，不管系統存檔機制有沒有把設定留住都無所謂。

## 驗證方式

改完不是只憑推理相信會動，是**真的重開機測試**：重開機後 `/proc/asound/cards` 顯示編號真的又跟之前不一樣了（card 0/1 對調），確認：
- 程式自動偵測到新的正確卡號
- 音量在新的正確卡號上自動設定成 -10dB
- 觸發播放後 `mpv` process 的 `--audio-device` 參數用的是正確的卡號

---

# LINE 機器人：歌手推薦 + `@` 提及點歌

使用者想要更貼近日常對話習慣的點歌方式：不知道歌名時能推薦熱門歌曲、可以用「@叫它」的方式點歌，而不是死板地一定要打「點歌」兩個字。這次改動全在 `karaoke.py` + `line_control.py`，走完整的 Plan Mode 流程（先寫計畫檔、使用者核准後才動手）。

## 做了什麼

1. **`karaoke.py` 新增 `search_top_songs(keyword, count=5)`**：用 `yt-dlp --flat-playlist` 搜尋 `"<關鍵字> 熱門歌曲"`，回傳前 N 筆 `{'title', 'id'}`。用 `--flat-playlist` 是因為不需要逐一解析每部影片的播放格式，只要基本資訊，明顯比完整解析快。這不是正式排行榜資料，是 YouTube 搜尋排序，但對主流歌手已經夠準。

2. **`line_control.py` 新增 `@` 提及點歌**：`@任何稱呼 歌名`（例如「@小樂 稻香」）跟「點歌 歌名」做同一件事，故意不檢查 `@` 後面那個稱呼是不是「小樂」——只要有 `@` + 空白 + 內容，就當點歌處理。跟「點歌」前綴共用同一段「解析尾綴0→伴奏版、加入排隊、組回覆」邏輯，抽成 `_queue_song_from_text()` 這個 helper，避免程式碼重複。

3. **新增「推薦 <歌手>」→「回數字直接點歌」的兩步驟流程**：
   - 觸發詞很寬鬆：`推薦 X`、`介紹 X`、`X的歌`、`X有什麼歌`、`X推薦` 都算，用 `_extract_recommend_keyword()` 判斷。
   - 觸發後回傳搜尋到的前 5 首歌名清單，存進 `_pending_recommendations[user_id]`（含時間戳記）。
   - 使用者接著回一個 1~5 的數字，就直接把對應那首加入排隊，不用再打一次歌名。

## 最大的坑：數字鍵已經被 LED 指令佔用

`handle_command` 裡數字 `1`～`6`、`0` 從很早以前就是控制 LED 燈泡的指令（`1`=燈泡1長亮…）。如果讓「回數字選推薦歌曲」直接搶走這些數字，會整個弄壞既有功能。

**解法**：`_pending_recommendations` 用 `user_id` 分開記錄，且**只有在該使用者剛好有「未過期的待選清單」時**，數字 1~5 才會被攔截去做點歌；沒有待選清單、或超過 120 秒沒回應（TTL 過期），數字鍵一律照舊是 LED 指令，行為完全不變。這個攔截判斷刻意放在 `handle_command` 最前面（比 LED 判斷更早檢查），檢查完是不是「合法待選中的選歌回覆」，不是就直接放行讓後面的 LED 判斷接手。

`6` 跟 `0` 完全不受影響——推薦清單最多給 5 首，這兩個數字永遠是 LED 指令。

## 驗證方式

- 本地：`handle_command('@小樂 稻香', ...)`、尾綴 `0` 伴奏版判斷、`_extract_recommend_keyword()` 對五種觸發語法的判斷、手動塞 `_pending_recommendations` 後確認數字鍵正確攔截且用後即丟（one-shot）、不同 `user_id` 之間不會互相干擾、TTL 過期後數字鍵恢復 LED 行為——全部用假設定檔在本地測過一輪。
- 意外發現並修掉一個既有小 bug：`karaoke.py` 的 `_resolve_youtube()`／`search_top_songs()` 原本只 catch `subprocess.TimeoutExpired`，沒 catch `yt-dlp` 執行檔本身找不到的 `OSError`（`FileNotFoundError` 是它的子類別）。在樹莓派上不會觸發（yt-dlp 有裝），但這是本地測試時發現的真實健壯性缺口，兩處都補上 `OSError`。
- 真實部署到樹莓派 4 後端對端測試（跟一路的做法一樣，打真實簽章的 LINE webhook）：
  - 「推薦 周杰倫」→「1」，確認 `karaoke.get_status()` 真的加入了正確的歌曲，`title` 過幾秒後正確解析成真實影片標題
  - 「@小樂 小星星」，確認正確加入排隊
  - 傳一個全新、沒有待選清單的使用者傳「1」，用 `pinctrl get 5` 直接讀 GPIO 電位（不是看 log，因為 log 又遇到跟之前一樣的 stdout buffering 問題，systemd journal 一時看不到 print 輸出）確認真的是燈泡指令被觸發、不是誤判成選歌，證實新邏輯沒有破壞舊功能。

三項都確認正確後才回報修好。這個修法的重點是「讓程式適應環境，而不是硬記一個當下觀察到的值」——寫死 `hw:1,0` 這件事本身就是上次修 bug 時的疏漏，這次順便把它變成真正健壯的做法。

---

# 網頁點歌頁面：已播歌曲紀錄 + 推薦排除已播過的

## 做了什麼

1. **`karaoke.py` 新增播放歷史紀錄**：模組層級的 `_history` list（上限 30 筆，超過自動丟掉最舊的），在 `_player_loop()` 裡每次歌曲開始播放、標題解析完成後就記一筆（`_record_history()`），內容含標題、YouTube 影片 ID、完整網址、原聲/伴奏模式、點歌人、播放時間戳記。不管是使用者手動點歌還是熱門電台自動播的，都會記錄，因為都走同一個播放迴圈。
   - `get_history(limit=20)`：回傳最近播過的（新到舊排序），給網頁面板用。
   - `get_played_video_ids()`：回傳所有播過的 YouTube 影片 ID 集合，給推薦功能排除用。

2. **`/api/karaoke/status` 回應多一個 `history` 欄位**，前端既有的 1.5 秒輪詢機制順便一起更新，不用另外開新的輪詢。

3. **`/karaoke` 網頁新增「🕘 已播歌曲」卡片**：列出最近播過的歌，每一列可以整列點擊、也有獨立的 🔁 按鈕，兩者都是呼叫**既有的** `/api/karaoke/add` API、把歷史紀錄裡存的**確切網址**（不是歌名）當作 `query` 傳回去——這樣重播保證是同一部影片，不會因為重新搜尋而選到不同的版本。沒有新增後端 API，只是重用。

4. **`search_top_songs()` 加 `exclude_ids` 參數**：推薦歌手時（`推薦 <歌手>` 指令）現在會傳入 `karaoke.get_played_video_ids()`，過濾掉已經播過的。因為排除後候選可能不夠 5 首，搜尋時刻意多抓一點（`count + len(exclude_ids) + 5` 筆候選）再篩選，確保排除完還是儘量湊滿 5 首。

## 驗證方式

- 本地：手動塞 `_record_history()` 資料，確認 `get_history()` 排序正確（新的在前）、`/api/karaoke/status` 的 `history` 欄位正確帶出、透過 `/api/karaoke/add` 重播歷史紀錄裡的網址能正確加入排隊。
- 網頁視覺：本地起了個假的 Flask app 匯出 `KARAOKE_HTML`，在瀏覽器裡塞假資料確認「已播歌曲」卡片排版、深色模式、點擊/按鈕互動都正常，主控台沒有 JS 錯誤。
- 真實部署到樹莓派 4 端對端測試時，意外發現一個很好的驗證機會：測試當下使用者自己在手機 LINE 上開著 K-pop 熱門電台在真實播放，已播清單即時、正確地記錄了 BTS、TWICE、aespa 等實際播出的歌曲——用真實的、非我觸發的使用流量驗證了歷史紀錄功能，比自己寫測試資料更有說服力。過程中沒有中斷使用者正在聽的音樂。

---

# 2026-07-20：LINE 點歌機器人接上 openclaw + Bionic 本地模型，做自然語言翻譯

## 背景：openclaw 調查的來龍去脈

使用者本機 Mac 上另外裝了一套叫 **openclaw** 的工具（`github.com/openclaw/openclaw`，npm 套件，「多管道 AI Gateway」，本機跑在 port 18789），還有 **Bionic**（LM Studio 的改名版，本機模型下載/推論工具，CLI 在 `~/.lmstudio/bin/lms`）。使用者一開始問的是「怎麼把 openclaw 裡『小龍蝦』的模型換成本地的」，調查後發現：

- openclaw 裡目前只有一個預設 agent（`main`），並沒有叫「小龍蝦」的 agent——`~/.openclaw/workspace/IDENTITY.md` 還是空模板，代表使用者原本就打算幫某個 agent 取這個名字，但沒做完。
- **`~/.openclaw/openclaw.json` 裡的 `channels.line` 設定，跟這個樹莓派專案用的是同一個 LINE 官方帳號**（channel secret 完全一樣）。兩邊沒有真的衝突，因為 LINE 後台的 Webhook 網址目前指向樹莓派的 ngrok，openclaw 那邊的 LINE plugin 雖然 `enabled: true` 但沒有實際收到任何流量——**這只是一個潛在風險點，要記住：如果以後不小心把 LINE 後台的 Webhook 網址改指向 openclaw，兩套系統就會同時收到訊息、行為衝突**。

問清楚之後，使用者真正要的不是「兩個機器人」，而是：**讓現有這個樹莓派 LINE 點歌機器人聽得懂口語**（不是只認「點歌」「推薦」這些固定前綴），並且明確要求翻譯要透過 **openclaw 接上 Bionic 的本地模型**來做（不要走 Mac 上也有裝的 Ollama）。

## 最終架構

```
LINE 使用者口語訊息
  → 樹莓派 line_control.py 的 handle_command() 比對所有既有規則，都比對不到
  → 呼叫新增的 nlu.py 的 translate(text)
  → HTTP POST 到 Mac 的 openclaw gateway（http://<mac>:18789/v1/chat/completions，
     model="openclaw/karaoke-nlu"）
  → openclaw 把請求轉給新建立的 karaoke-nlu 這個 agent（模型指到 Bionic 本地跑的 qwen3-8b）
  → 模型把口語翻成機器人指令格式的一行文字（例如「點歌 稻香」），或回「無法辨識」
  → 樹莓派拿到這行文字，直接遞迴丟回 handle_command()，重用全部既有規則去執行，
     不用另外寫一套 action dispatch
  → 還是比對不到的話，就跟改動前完全一樣，回「不認識的指令」
```

**為什麼是「Pi 呼叫 openclaw、openclaw 再呼叫 Bionic」這個兩層架構，而不是 Pi 直接打 Bionic**：使用者明確要求要用 openclaw 做這個翻譯層（不只是把 Bionic 當一個普通的模型 API 用），這樣以後如果要換模型/加其他自然語言功能，都在 openclaw 這一層調整就好，樹莓派端的程式碼不用再動。

## Mac 端設定變更（不在這個 git repo 裡，記在這裡避免以後忘記）

用 `openclaw config patch`（不是手動改 JSON，這個指令會先跑 schema validation，比較不會手滑改壞設定）對 `~/.openclaw/openclaw.json` 做了這些變更：

1. **新增 `models.providers.lmstudio`**：指向 `http://localhost:1234/v1`（Bionic 本機伺服器，只需要綁 localhost，因為呼叫它的 openclaw 就跑在同一台機器上，不用讓它對外）。
2. **新增 `agents.list`**（原本這個 key 不存在，只有隱含的預設 agent）：
   - 明確列出 `{id: "main", default: true}`，不設任何 override，讓它繼續 100% 沿用原本的 `agents.defaults`（還是用 ollama/llama3.2:3b，完全不受影響）。
   - 新增 `karaoke-nlu`（顯示名稱設成「小龍蝦」——算是把使用者最一開始想做的事情做掉了）：`model: "lmstudio/qwen/qwen3-8b"`、`tools: {profile: "minimal", deny: ["session_status"]}`（見下面安全考量）、`contextInjection: "never"`（不要注入 main 的 AGENTS.md/SOUL.md，system prompt 完全自己控制，避免污染小模型的輸出格式）。
3. **`gateway.bind` 從 `"loopback"` 改成 `"lan"`**：讓同區網的樹莓派連得到 18789 port。
4. **開啟 `gateway.http.endpoints.chatCompletions.enabled`**：這個 OpenAI 相容端點預設是關的。

⚠️ **安全考量**（不是隱藏起來的細節，有跟使用者講清楚才做）：`gateway.auth.mode: "token"` 這個模式下，`/v1/chat/completions` 端點文件明講「把這個當成完整的 operator 權限」——樹莓派 `pi3_line_config.json` 裡存的這組 `nlu_token`，理論上可以拿去打 `main`（有完整 coding 工具權限，含檔案讀寫/執行指令），不是只能用在翻譯這個用途上。緩解做法：`karaoke-nlu` 這個 agent 本身設了 `tools.profile: "minimal"` 加 `deny: ["session_status"]`（等於零工具），所以就算被打，這個 agent 本身做不了任何危險的事；但 token 外洩的風險等級要跟 LINE channel secret 一樣看待。

## 樹莓派端新增/修改

- **新增 `nlu.py`**：只匯出一個 `translate(text) -> str | None`，讀 `pi3_line_config.json` 新增的 `nlu_base_url`/`nlu_token`/`nlu_enabled` 三個欄位。任何失敗（連不到、逾時 8 秒、格式不對、模型回「無法辨識」）一律回 `None`。
- **`line_control.py`**：`handle_command()` 最尾端、原本的「不認識的指令」catch-all 之前，插入 NLU fallback——`translated = nlu.translate(key)`，有翻譯結果就**遞迴呼叫 `handle_command(translated, ...)`**，讓翻譯出來的文字重新走一次前面所有既有規則。這個設計刻意不用 JSON 結構化輸出（本來想過，但因為請求是走 openclaw 的完整 agent run 而不是直接打 model API，中間會經過 agent 的一般對話處理流程，不保證每次都遵守 JSON schema），改成「輸出一行既有指令格式的純文字」更穩，而且完全不用另外寫 dispatch。
- `pi3_line_config.json` 新增 `nlu_base_url`（`http://lpldeMac-mini-2.local:18789`，用 Mac 的 mDNS 名稱不用寫死 IP，比較不怕路由器重新分配 DHCP）、`nlu_token`、`nlu_enabled: true`。

## 本地模型選擇：中間繞了一圈

一開始用 Bionic 已經下載好的 `google/gemma-4-e4b`（4B）測試翻譯品質，結果很不穩（約五到七成準確率，同一句話重跑還會給不同答案，甚至出現過幻覺輸出內部工具路徑 `>MEDIA:file:///__openclaw__/canvas/documents/kpop.mp3` 這種完全編造的東西）。跟使用者確認後，改用 `lms get qwen/qwen3-8b --mlx` 下載了一個更大的模型（4.62GB，MLX 4bit），品質明顯提升到七成左右正確、其餘三成安全地落到「不認識的指令」（不會做錯事，只是沒聽懂）。

這裡有兩個值得記住的教訓：
1. **透過 openclaw 的 agent run 呼叫模型，跟直接打模型的原生 API 不一樣**——即使把 `tools.profile` 設成最嚴格的 `minimal` 甚至 `deny` 掉僅剩的工具，小模型還是會不時「動作幻覺」（輸出看起來像工具呼叫或內部路徑的東西），這是 agent 執行框架本身的行為模式，不是單純調 prompt 或關工具就能完全根除的。
2. **這個功能設計本身有容錯能力，所以品質沒到 100% 也還能上線**：`nlu.py` 翻譯失敗或翻出無法辨識的格式，一律回 `None`，`handle_command()` 會直接落到「不認識的指令」，不會誤觸發任何動作（尤其不會碰到 LED/蜂鳴器/繼電器——system prompt 明確禁止輸出這類指令，且就算模型亂翻，`handle_command()` 裡硬體相關的規則檢查在最前面，NLU 只是最後一道 fallback，兩層保護）。

如果之後想繼續提升翻譯品質，方向是：換更大的模型（qwen3-8b 已經是這台 Mac mini M4 16GB 記憶體撐得起的合理上限，再大可能會擠壓其他本機程式的記憶體）、或是研究 openclaw 有沒有「不經過完整 agent run、直接打 provider 原生 API」的呼叫方式（如果有的話應該會比透過 agent run 穩定很多）。

## 驗證方式（都在真實樹莓派 4 上跑過，不是紙上談兵）

- Mac 端：`lms server start --port 1234` 後 `lms ps` 確認模型有載入，`openclaw config patch --dry-run` 先驗證過設定沒問題才真的套用，`openclaw gateway restart` 後本機 `curl localhost:18789/v1/models` 確認 `openclaw/karaoke-nlu` 有出現在清單。
- 從樹莓派 SSH 出去 `curl http://lpldeMac-mini-2.local:18789/v1/models` 確認區網連得到（mDNS 名稱能正確解析）。
- 組簽章正確的假 LINE webhook payload 直接打樹莓派本機 IP 的 `/callback`（不用特地繞去 ngrok），透過 `/api/karaoke/status` 確認：
  - 既有規則（`1`＝LED、`點歌 小星星`、`@小樂 稻香`、`推薦 周杰倫` 後回`1`選歌）行為跟改動前完全一樣。
  - 口語訊息（「我想聽五月天的溫柔」「可以跳過這首嗎」）能正確加入排隊/切歌。
  - 完全無關的訊息（「今天天氣如何」）不會誤加歌曲，安全地什麼都不做。
  - 手動把 Mac 上的 openclaw gateway 停掉，模擬離線，口語訊息在 8 秒逾時內安全回退成「不認識的指令」，不會卡住或讓 Flask process 掛掉。
- 測試完把樹莓派上的播放佇列用「停止」指令清空，沒有留下測試垃圾在正式佇列裡。

## 順手修的一個 bug：播放「成功」但沒聲音

上面這些都測完之後，使用者實際點歌回報「網頁顯示點播成功、已經在播放階段，但完全沒聲音，然後就直接結束了」。查的時候發現一個程式碼層面的盲點：`_record_history()` 是在 `_resolve_youtube()` 解析成功「之後」、`mpv` 真正啟動「之前」就呼叫的，所以「有出現在已播歌曲清單、網頁顯示正在播放」**不代表 mpv 真的有成功播出聲音**。而且 `_player_loop()` 呼叫 mpv 時用的是 `--really-quiet` + `stdout=DEVNULL, stderr=DEVNULL`，就算 mpv 真的播放失敗，錯誤訊息也是直接丟掉，完全查不到原因。

改成 `--quiet`（只關掉逐秒進度列，警告/錯誤還是會印）+ 把 stdout/stderr 導到 `/tmp/mpv_karaoke.log`（每首歌開始播放時用 `'w'` 模式重開，所以檔案內容永遠是「最近一首歌」的 mpv 輸出，不會無限長大）。修完後重新點播同一支影片重現測試，這次透過 `_mpv_query('time-pos')` 確認 mpv 真的有在推進播放進度（`time_pos` 從 0 開始正常增加），log 檔案也乾淨沒有警告，判斷是暫時性問題（沒有重現到真正的播放失敗）。

這次沒能重現原始的無聲問題，所以沒辦法 100% 確定根本原因，但至少下次再發生的話，`/tmp/mpv_karaoke.log` 會留下 mpv 自己的錯誤訊息，不用再靠猜的。

## 已播歌曲/推薦重複的問題：改成「同一首歌」比對 + 12 小時過期

使用者接著回報兩個相關的問題：(1) 推薦歌曲沒多久就會重複，(2) 已播歌曲清單想要每 12 小時清一次釋放記憶體。查了一下發現這兩個問題其實是同一個根因：

- **舊的排重是用 YouTube 影片 ID 精確比對**（`get_played_video_ids()`），但同一首歌常常有好幾個不同影片 ID（官方版、合輯裡收錄的、不同頻道轉載的），搜尋結果排序一變就可能選到「ID 不同但其實是同一首歌」的版本，ID 比對完全抓不到，使用者感覺就是「推薦一直重複」。
- **舊的已播歷史是用「最多 30 筆」的固定筆數上限**（`_HISTORY_MAX = 30`），熱門電台開著跑的話很快就會塞滿 30 筆，舊紀錄被擠掉，等於「忘記」自己剛播過那首歌，推薦/電台就會選到看似很久沒播、其實幾分鐘前才播過的歌。

**改法**：
1. **`_normalize_title()`**：把 YouTube 標題正規化成一個比對用的 key——先拿掉「Official Music Video」「高清」這類宣傳雜訊詞跟括號符號（但保留括號裡的文字，很多標題把歌名放在括號裡，例如「周杰倫【稻香】」），有中文字的話優先取「純中文字元」當 key（比整串比對穩，不受前後的英文/羅馬拼音/頻道名影響），沒有中文字（英美韓文歌名）才退回用整串英數字比對。實測「周杰倫 Jay Chou【稻香 Rice Field】-Official Music Video」跟「周杰倫 - 稻香 (Rice Field) Official Audio」兩個標題會正規化成同一個 key。
2. **已播歷史從「固定 30 筆」改成「12 小時過期」**（`_HISTORY_TTL = 12 * 3600`），`_HISTORY_MAX` 改成 500 純粹當安全上限（正常情況下靠 TTL 就會控制在很小的數字）。`_prune_expired_history()` 在每次寫入新紀錄、以及每個查詢函式（`get_history`/`get_played_video_ids`/`get_played_queries`/`get_played_title_keys`）裡都會先跑一次，把最舊的、超過 12 小時的紀錄丟掉——因為 `_history` 是照時間遞增 append 的，只要從最前面丟到第一筆沒過期的就能停，不用整份掃。
3. **`search_top_songs()`** 新增 `exclude_title_keys` 參數，除了原本的 ID 排除，現在也用 `_normalize_title()` 排除「同一首歌不同版本」；同一批搜尋結果內部也順便排重（避免同一次推薦裡官方版跟合輯版都出現）。
4. **`_pick_radio_song()`** 改用 `get_played_queries()`（12 小時內播過的原始查詢字串，例如熱門清單裡的「周杰倫 稻香」）取代原本「只排除最近 5 首」的 `_radio_recent` 機制——排重窗口從「5 首」變成「12 小時」，明顯更長。因為每個分類目前只有 12 首，如果 12 小時內整個分類都播過一輪，會自動退回允許重複（清單本來就小，這是必然的，不是 bug）。
5. **`點歌 <歌名>` 手動點播完全不受影響**：`add_song()` 本來就不會呼叫任何排重邏輯，所以「除非點播，不然不要重複播放」這條規則是自然成立的——排重只發生在「推薦」候選過濾跟「熱門電台」自動選歌這兩個地方，使用者自己指定歌名一定會播。
6. `_record_history` 現在也存 `song.query`（原始查詢字串），不是只存解析後的 YouTube 標題——`get_played_queries()` 排重要用。

驗證：本地寫了一份不需要 GPIO/yt-dlp 的單元測試（假造 `_history` 內容、monkeypatch `subprocess.run` 模擬 yt-dlp 輸出），確認：過期紀錄真的會被清掉、電台選歌會避開最近播過的、整個分類都播過一輪後會優雅退回允許重複、推薦結果會正確排除「ID 不同但標題正規化後相同」的重複。部署到樹莓派後用真實 LINE webhook 送「推薦 周杰倫」確認正常回應、沒有噴錯。

---

# 2026-07-21：修點歌人辨識 bug、大螢幕歌詞頁面、語音點歌

使用者一次提了三件事，分開記錄。

## 1. 修 bug：點歌人有時候會被誤判成「匿名」

`get_display_name(user_id)` 原本的邏輯是：查 LINE Get Profile API，不管成功失敗都把結果寫進 `_display_name_cache[user_id]`。問題是「失敗」也會被快取——如果剛好那一次 LINE API 逾時或網路不穩（8 秒逾時不算長），這個使用者就會被永久卡成「匿名」，直到服務重啟為止，之後每次點歌都查不到真名，即使 LINE API 本身早就恢復正常。

改法很單純：**只有成功查到名字才寫入快取**，失敗的話這次先回「匿名」但不快取，下次同一個人點歌會重新試著查一次，不會被一次性的網路問題卡死。

## 2. 大螢幕歌詞頁面（`/display`）

使用者想要接電視/顯示器當 KTV 大螢幕用，但手邊暫時沒有 HDMI 線，所以這次先把頁面做好、部署上線，等有線材再實際測試投影效果。

新增 `DISPLAY_HTML` + `/display` 路由，風格延續 `KARAOKE_HTML` 既有的視覺語言（深色背景、漸層品牌色、旋轉唱片動畫），但版面整個重新設計成「電視觀看距離」的比例：
- 超大字體同步歌詞（像跑馬燈提詞機，目前行 4.2vw、前後行 2vw，比手機版的字級大非常多）
- 現正播放的封面（旋轉唱片）+ 歌名 + 點歌人，固定在畫面上方
- 畫面底部固定顯示「接下來」的排隊清單（最多 4 首）
- 沒有播放中時顯示「等待點歌中...」的待機畫面，附上怎麼點歌的提示
- 右上角常駐小字提示「在 LINE 傳『點歌 歌名』」，因為這個頁面本身沒有任何可點擊的互動元件（電視/投影機通常沒有滑鼠鍵盤）

沿用既有的 `/api/karaoke/status` 每 1.5 秒輪詢機制，沒有新增後端 API。LINE 傳「大螢幕」（或「大屏」「投影」「display」「tv」）會回傳這個頁面連結。

驗證：這個 Browser 環境的沙盒會擋掉樹莓派區網 IP 跟 localhost 的存取（需要另外手動批准），所以沒辦法直接截圖看樹莓派上的實際渲染結果，改成把同一份 HTML/CSS/JS 配上假資料發布成 Artifact 預覽（模擬待機/播放中兩種狀態），視覺上跟部署到樹莓派上的是同一份程式碼，邏輯上沒有差異。實際接上電視後如果比例/字級不順眼，微調對應的 vw 數值即可。

## 3. 語音點歌

使用者想要傳語音訊息也能點歌，不用打字。openclaw 內建的語音轉文字全部是雲端 provider（Deepgram、OpenAI、Google 等等），沒有本地選項，所以另外**獨立於 openclaw** 架了一個本機語音轉文字服務：

- **Mac 端新增 `~/.whisper_server/whisper_server.py`**：獨立的小 Flask app（自己的 venv，Python 3.12 + `mlx-whisper` + `flask`），用 `mlx-community/whisper-large-v3-turbo` 模型（~1.6GB，Apple Silicon 上跑得快，中文專有名詞辨識也比小模型準），監聽 port 8765，`POST /transcribe` 收音檔位元組、回傳辨識文字。另外裝了 `ffmpeg`（Homebrew）給 mlx-whisper 解碼音訊用。目前是手動 `nohup ... &` 啟動的，不是 launchd 常駐服務——Mac 重開機或這個 process 被殺掉的話需要手動重開，之後有空可以比照 Bionic/openclaw 那樣設成開機自動啟動。
- **樹莓派新增 `stt.py`**：跟 `nlu.py` 平行的獨立模組，`transcribe(audio_bytes) -> str | None`，讀 `pi3_line_config.json` 新增的 `stt_base_url`/`stt_enabled`。任何失敗一律回 `None`。
- **`line_control.py` 的 `/callback`**：原本只處理 `message.type == 'text'`，其他類型（含語音）直接跳過。現在多處理 `'audio'` 類型：`_download_line_audio(message_id)` 用 LINE 的 Content API（`GET https://api-data.line.me/v2/bot/message/{id}/content`，跟 `get_display_name()` 用的是同一種 Bearer token 認證方式）把語音訊息的音檔下載下來，丟給 `stt.transcribe()` 轉文字，轉出來的文字**直接丟回 `handle_command()`**——跟語音辨識完全無關的既有規則、@提及、推薦、NLU fallback 全部原封不動重用，不用另外寫一套。回覆會先顯示「🎤 聽到你說：『...』」再接實際處理結果，讓使用者能發現辨識錯誤（語音辨識不可能 100% 準，尤其是歌名這種專有名詞，這一步是刻意的透明度設計，不是可有可無的細節）。

**驗證時發現的真實案例**：拿 macOS 的 `say` 指令生成一句測試語音「我想聽周杰倫的稻香」轉成 m4a，直接打 Mac 本機的 whisper server 辨識結果是「稻香」完全正確；但同一個音檔透過樹莓派整個網路路徑（Pi 下載音檔的等效測試 → 打 Mac 的服務）再測一次，這次辨識成「道香」——「稻」「道」是完全同音字，這是語音辨識模型本身的合理誤判（尤其 `say` 合成的語音音調比真人說話更平，同音字更難靠語氣分辨），不是程式邏輯的 bug。這正好驗證了「回覆先顯示聽到的內容」這個設計是必要的，不是多餘的。

**沒辦法測到的部分**：`_download_line_audio()` 這個下載音檔的函式，因為需要一個真實的 LINE 語音訊息 message id 才能實際呼叫 LINE 的 Content API，沒辦法用假造的 webhook payload 測試（這點跟文字訊息不一樣，文字訊息整個 payload 都可以自己組)。這段程式碼的認證方式完全比照已經驗證過能正常運作的 `get_display_name()`，風險評估上覺得可以接受，但最終還是需要使用者實際傳一則語音訊息來完整驗證這條路徑。

## 這次沒做但先记录下来的：

- Whisper server 目前沒有任何身份驗證（純 LAN 內網、不需要密鑰），因為它只是一個「音檔進、文字出」的純函式服務，沒有像 openclaw 那樣可以執行危險操作的疑慮，風險評估上刻意選擇簡化掉這一層。

---

# 2026-07-21（續）：Mac 服務開機自動啟動 + 樹莓派大螢幕 kiosk 模式

上面提到「Whisper server 需要手動啟動」寫完沒多久，使用者就回報兩件事：(1) 樹莓派裝的是無圖形介面的版本（Raspberry Pi OS **Lite**），接 HDMI 也只會看到文字終端機，`/display` 頁面根本沒有瀏覽器可以顯示；(2) 擔心 Mac 上這些服務（Bionic 伺服器、Whisper server）忘記手動啟動。兩個都處理了。

## Mac 端：Bionic + Whisper server 改成開機自動啟動

用 `launchd`（macOS 原生機制，openclaw 自己的 gateway 本來就是這樣裝的，見上面章節的 `ai.openclaw.gateway.plist`），裝了兩個新的 LaunchAgent：

1. **`~/Library/LaunchAgents/com.lpl.bionic-server-start.plist`**：登入時執行一次 `lms server start --port 1234`。這裡有個關鍵發現：`lms server start` 本身執行很快就結束（不到 1 秒），不是常駐 process——它是在跟 Bionic 背景服務「喊話」說「該開 API 伺服器了」。實測**把 Bionic.app 整個關掉**之後執行 `lms server start`，還是印出「Waking up LM Studio service...」然後成功，背後自動啟動了一個 `Bionic --run-as-service` 的無 GUI 精簡模式（不是完整開一個視窗），代表這個 LaunchAgent 不需要額外設「開機自動打開 Bionic.app 本體」。所以這個 plist 只有 `RunAtLoad`，沒有設 `KeepAlive`（因為它本來就该很快跑完退出，設 KeepAlive 反而會被 launchd 誤判成「一直在 crash」而狂重啟）。
2. **`~/Library/LaunchAgents/com.lpl.whisper-server.plist`**：這個才是真正常駐的 process（`whisper_server.py` 本身），設 `RunAtLoad` + `KeepAlive`（跟 openclaw 的 gateway 一樣的設定，crash 了會自動重開）。

兩個都用 `launchctl load` 載入並實測過重新啟動有效（先手動關掉舊的手動啟動的 process，改成完全交給 launchd 管）。之後 Mac 重開機、或這兩個 process 意外被殺掉，都會自動再起來，不用再手動記得啟動。

## 樹莓派端：`/display` 大螢幕 kiosk 模式

樹莓派裝的是 Raspberry Pi OS **Lite**（一開始整個專案就是刻意選 headless 版本方便 SSH 遠端操作），完全沒有桌面環境，所以就算接了 HDMI，畫面只會停在文字終端機，看不到任何網頁。要讓 `/display` 頁面真的能投影出來，得裝一套最小可用的圖形環境：

1. **裝套件**：`xserver-xorg`（X 伺服器本體）、`xinit`（提供 `startx`）、`x11-xserver-utils`（`xset` 這些工具，用來關掉螢幕保護程式/DPMS 省電模式，不然電視放著放著會自動黑屏）、`chromium`（瀏覽器）、`unclutter`（閒置時自動隱藏滑鼠游標）。這台樹莓派的系統碟還有 23GB 空間，裝這些綽綽有餘。
   - 過程中有個小插曲：第一次下指令因為 expect 腳本的密碼提示比對邏輯沒處理好，SSH session 提前斷線，但背景的 `apt-get install` 其實已經在樹莓派上繼續跑（沒有真的中斷），第二次重下指令時撞到 dpkg lock 才發現——確認過那個殘留的 process 真的還在正常安裝中（不是卡死），所以就等它跑完，沒有手動殺掉重來。
2. **開機自動登入到文字終端機**：`sudo raspi-config nonint do_boot_behaviour B2`（等同 `raspi-config` 圖形選單裡的「Console Autologin」），設定 `lpl1103` 這個帳號開機後自動登入 tty1，不用再手動輸入帳密。
   - ⚠️ 這代表**有實體接觸這台樹莓派的人不用密碼就能拿到一個已登入的終端機**（跟現有「LINE 上任何加好友的人都能操作機器人」是類似等級的信任假設，樹莓派本來就放在家裡，跟這個專案一路的風險接受度一致，這裡明講出來讓使用者知情，不是自己偷偷決定）。
3. **`~/.profile` 加一段自動判斷**：只有滿足「沒有 `$DISPLAY`（代表還沒進圖形模式）」且「`tty` 是 `/dev/tty1`（代表是實體螢幕登入，不是 SSH 進來的）」才會執行 `startx`——這樣以後 SSH 連進去做維護完全不受影響，只有接電視那個實體登入才會觸發開瀏覽器。
4. **`~/.xinitrc`**：關掉螢幕保護程式/DPMS、啟動 `unclutter`、**等 `line-control.service` 的網頁伺服器真的啟動**（用 `curl` 輪詢 `/display` 最多 30 秒，因為開機時 X 通常比 Flask app 先準備好，太早開瀏覽器會卡在連線失敗的畫面）、最後用 `chromium --kiosk --incognito ...` 全螢幕開啟 `http://localhost:8000/display`（無邊框、無工具列、無痕模式不留快取/紀錄）。
5. 確認過 `/etc/X11/Xwrapper.config` 的 `allowed_users=console` 設定跟這套「console 自動登入再跑 startx」的架構是相容的，不需要額外調整權限（不用改成風險較高的 `allowed_users=anybody`）。

**沒辦法驗證的部分**：這一整套「開機 → 自動登入 → 自動開瀏覽器全螢幕」的流程，需要實際重開機 + 有一台螢幕接在樹莓派上才能親眼確認畫面真的有跑起來——我只能透過 SSH 確認每個檔案/設定都正確就位（套件裝好了、autologin 設定檔存在、`.profile`/`.xinitrc` 內容跟語法都對、`Xwrapper.config` 權限模型相容），但沒辦法遠端看到實際的視覺輸出。使用者拿到 HDMI 線接上電視、重開機一次之後，才是真正的最終驗證。如果畫面沒有如預期出現，`~/.xinitrc` 裡的每一步都可以先手動在樹莓派主控台上一行一行執行来排查是哪個環節卡住。

## 補充：`getty@tty1` 改了設定不會自動生效

使用者接了 HDMI 之後回報螢幕還是卡在文字終端機。查了才想到一個明顯但一開始漏想的環節：`raspi-config nonint do_boot_behaviour B2` 只是把 autologin 的設定檔寫下去，**不會讓已經在跑的 `getty@tty1` 服務重新讀取這份設定**——這台樹莓派當時已經開機 23 小時，`getty@tty1` 從那時候就一直用「舊」的（沒有 autologin）方式在跑。不用整台重開機，`sudo systemctl restart getty@tty1.service` 就能讓它用新設定重新啟動這一個服務，完全不影響 `line-control.service`（背後的點歌系統）。之後只要樹莓派本身有重開機過（不管是斷電還是正常重啟），這個問題就不會再出現，因為開機流程本來就會用最新的設定啟動 `getty@tty1`。

## 螢幕接上後發現的兩個真實 bug

使用者接上 HDMI、`getty@tty1` 重啟生效後，實際看到畫面回報了兩個問題，都修了：

1. **歌詞顯示出一堆 `<00:00.000>` 這種標記，不是正常歌詞**：`karaoke.py` 的 `_parse_lrc()` 只有處理每行開頭的 `[mm:ss.xx]` 時間標記，但 lrclib.net 有些歌的同步歌詞是「逐字歌詞」格式，每個字前面還會多插一個 `<mm:ss.xxx>` 的行內時間標記（用來做逐字高亮動畫），例如 `[00:00.000]<00:00.000>青<00:00.366>花<00:00.732>瓷...`。這些行內標記之前完全沒被濾掉，整段被當成歌詞文字顯示出來。加了 `_LRC_INLINE_TAG` 這個正則式把行內的 `<mm:ss.xxx>` 標記濾掉，只留下真正的字。**這個 bug 其實從歌詞功能一開始做的時候就存在**，只是手機版網頁字體小、加上剛好測試過的歌都沒踩到這種逐字歌詞格式，一直到接上大螢幕、字放很大才被注意到——這也是大螢幕模式意外帶來的一個好處（更容易發現這類本來就存在但不明顯的問題）。用截圖裡的原始資料寫了單元測試重現、確認修好，也重新點播同一首歌（周杰倫《青花瓷》）驗證線上環境真的正常了。
2. **中文字全部變成方框（缺字型）**：樹莓派是最小化安裝的 headless 系統，本來就沒有裝任何中文字型，Chromium 找不到中文字的字型資料，只能顯示「缺字框」。裝了 `fonts-noto-cjk`（Debian 官方套件，Google Noto Sans CJK，涵蓋中日韓文字，56.7MB），裝完 `sudo systemctl restart getty@tty1.service` 讓 kiosk 模式的 Chromium 重開一次才會吃到新字型（字型是瀏覽器啟動時讀取的，裝好當下不會馬上生效）。
3. **待機畫面的 🎤 emoji 沒顯示出來**：跟上面中文字缺字型是同一類問題，但 emoji 是另外獨立的字型套件——`fonts-noto-cjk` 只涵蓋中日韓「文字」，不含 emoji 這種彩色圖像字符。另外裝了 `fonts-noto-color-emoji`（10.1MB），一樣要 `sudo systemctl restart getty@tty1.service` 讓 Chromium 重開才生效。**這台樹莓派要顯示中文/emoji 正常，這兩個字型套件都要裝**，之後如果重灌系統或換一台新的樹莓派做這件事，記得兩個都要裝，缺一個都會有缺字問題。

---

# 2026-08-10 更新：推薦不重複、常點歌曲資料庫、天氣查詢（風扇未完成）

## 今天做了什麼

搬辦公室之後第一次回來動這個專案。使用者提了四個新功能，完成三個。

## ⚠ 環境變了，先看這個

**樹莓派 4 的 IP 從 `192.168.1.111` 變成 `192.168.0.17`**（搬辦公室，整個網段從
192.168.1.x 換成 192.168.0.x）。使用者的 Mac 現在是 `192.168.0.95`。

找機器的可靠方法（IP 會再變）：掃網段找開 22 埠的主機，再看 SSH banner——
樹莓派會回 `SSH-2.0-OpenSSH_10.0p2 Debian-7+deb13u4`（Debian 13 Trixie）。

Mac 的公鑰已加進 `~/.ssh/authorized_keys`，現在可以免密碼 SSH。
**不要代替使用者輸入系統密碼**（坑#10），需要密碼時請使用者自己執行。

---

## ✅ 1. 熱門電台一次播放期間不重複

**使用者的需求**：連續播 4 小時（約 60 首）不要重複；停止之後下次開始
有少部分重複沒關係。

**根因**：`POPULAR_SONGS` 是**寫死的清單，每類只有 12 首**，約 48 分鐘就繞完。
原本的程式註解自己也承認這點（「清單本來就小、遲早會繞回來的必然結果，不是 bug」）。
差了 5 倍。

**做法**：新增 [src/radio_pool.py](../src/radio_pool.py)

- 不再寫死歌單，改用 15~18 組**種子關鍵字**（歌手 + 曲風 + 年代）去 YouTube 抓，
  池子累積到數百首
- **背景預先補充**：播放中就一邊抓下一批，使用者不用等
- 兩層排除：
  - `_session_played` —— 這次電台開著期間播過的，**只在 `stop_radio()` 時清空**。
    硬性排除，池子不夠寧可去抓更多也不重複。**這是解決問題的關鍵。**
  - 12 小時歷史 —— 原本就有的，跨 session 的軟性排除

**樹莓派實測**：

    第  20 首  不重複  20  重複 0  池子  63
    第  40 首  不重複  40  重複 0  池子 129
    第  60 首  不重複  60  重複 0  池子 166   <- 4 小時
    第  80 首  不重複  80  重複 0  池子 210

池子成長比消耗快，所以播更久也不會重複。停止後重開實測 10 首裡有 6 首重疊（允許）。

**⚠ 踩到的坑**：`ytsearch` 的結果會混進**頻道**（不是影片），它的 `duration` 是 `NA`。
第一版寫「拿不到長度就放行」，池子第一筆就是「周杰倫 Jay Chou」這個頻道本身，
播下去只會失敗。**拿不到長度要直接跳過。**

---

## ✅ 2. 常點歌曲資料庫 + 快捷點歌

**新增** [src/song_stats.py](../src/song_stats.py)，SQLite 存在 `~/karaoke_stats.sqlite`。

**為什麼要另外存**：`karaoke._history` 是記憶體裡的 list、只留 12 小時，
服務一重啟就沒了。它的用途是「短期別重複播」，跟「這個人常點什麼」是不同需求。
所以不動它，另外開一份永久的。

**只記人點的，不記電台自動播的**——電台一小時放十幾首，記進去會淹沒真正的點播紀錄。
判斷方式是看 `requester` 是不是以 `🔀` 開頭。

**LINE 指令**（沿用推薦功能那套「回數字選歌」的機制，使用者不用學新操作）：

    常點 / 我的常點    -> 列出你最常點的前 5 首，回 1~5 直接點
    熱門排行          -> 全場最常被點的前 5 首

**⚠ 順手修的**：原本的數字選歌寫死用 `video_id` 組網址，但常點歌曲是從資料庫來的，
可能只有查詢字串沒有 id。已改成兩種都支援。

**已知限制**：正規化是「取中文字元照順序」，所以「稻香 周杰倫」和「周杰倫 稻香」
會算成兩首。實際使用時標題來自 YouTube（同一首歌標題固定）所以少見。
沒有改那個函式，因為它同時被去重邏輯使用，改動風險大。

---

## ✅ 3. 天氣查詢

**新增** [src/weather.py](../src/weather.py)。地點：新北市三重湯城（25.0616, 121.4790）。

用 **Open-Meteo**：免費、**不用申請 API key**、沒有額度限制。
用需要 key 的服務會多一個「key 過期就整個壞掉」的失效點。

座標寫死是刻意的——機器架在辦公室，地點不會變，做成可設定只是多一個會設錯的地方。

**LINE 指令**：`天氣` / `氣溫` / `溫度`

樹莓派實測輸出：

    🌤 新北市三重　毛毛雨　目前 27°C（體感 35°C）
    濕度 97%　今日 25~32°C　降雨機率 100%

---

## ⏸ 4. 博聯小黑豆紅外線控制風扇（未完成，明天繼續）

**程式已寫好**：[src/ir_remote.py](../src/ir_remote.py)，`python-broadlink 0.19.0`
已裝在樹莓派上。走**區網直連，不經過博聯雲端**——不需要帳號、不會因對方 API 改版
就壞掉、延遲只有幾十毫秒。

**卡在哪**：`ir_remote.py discover` 在區網裡**掃不到裝置**。

**明天要先確認的三件事**：

1. **小黑豆跟樹莓派是不是同一個網段？** 樹莓派在 `192.168.0.17`。
   博聯裝置**只支援 2.4GHz**，如果設定時手機連的是 5G 頻段，可能配到不同網段。
   最快的解法是從博聯 App 或路由器的裝置清單查到小黑豆的 IP，
   然後直接指定連線（不靠廣播探索——廣播常被路由器的 AP 隔離擋掉，
   這也是掃不到的常見原因）。
2. **有沒有通電**、燈是不是亮的。
3. **確認型號**：RM Mini 3（黑豆）／RM4 Mini／RM4 Pro，探索協定略有差異。

**⚠ 紅外線碼一定要現場學一次，沒有辦法自動化。**
手機 App 裡的碼存在博聯雲端，拿不到。做法是讓小黑豆進入學習模式
（`python3 ~/ir_remote.py learn fan_power`），**由人拿風扇遙控器對著它按一下**，
把訊號存進 `~/ir_codes.json`，之後就能無限重放。

最少學電源鍵就能開關；也可以學風速、擺頭、定時。

**已知的行為限制**：多數電風扇遙控器的電源是**同一顆鍵切換開關**，
所以「開風扇」跟「關風扇」送的是同一個碼，實際結果取決於風扇當下狀態。
這是遙控器本身的設計，不是程式沒做好。

---

## 相關檔案位置（新增）

| 檔案 | 用途 |
|---|---|
| `src/radio_pool.py` | 熱門電台的動態歌曲池、一次播放期間不重複 |
| `src/song_stats.py` | 點歌統計（SQLite，`~/karaoke_stats.sqlite`） |
| `src/weather.py` | 天氣查詢（Open-Meteo，免 key） |
| `src/ir_remote.py` | 博聯紅外線遙控（未完成） |

樹莓派上的部署位置都是 `~/`（跟既有的 `karaoke.py`、`line_control.py` 同一層）。
原本的 `karaoke.py` 已備份成 `~/karaoke.py.bak-<時間>`。

## ⚠ 還沒做的事

**服務還沒重啟**，所以上面三個新功能**還沒在正式服務上生效**。
檔案已經傳到樹莓派，但 `line-control.service` 跑的還是舊版程式。

明天要做的第一件事：

    ssh lpl1103@192.168.0.17 'sudo systemctl restart line-control'

（這台 sudo 需要密碼，見坑#9，要用 `ssh -t`）

重啟後要驗證的：
1. LINE 傳「天氣」有沒有正常回覆
2. LINE 傳「熱門 中文」開電台，看連續播幾十首有沒有重複
3. LINE 傳「常點」（要先有點歌紀錄才會有東西）

---

# 2026-08-11：三個新功能正式部署完成 + 抓到 ngrok 網域被搶走

接續上一節。使用者要求「正確部署好，先測試新增的 3 個功能」。結論：**三個功能全部
驗證通過並已在正式服務上生效**，但過程中發現一個上一節沒注意到、會讓 LINE 機器人
從外網完全失效的問題。

## 上一節說「服務還沒重啟」，實際上已經生效了

上一節留的待辦是「明天第一件事：`systemctl restart line-control`」。但實測發現
**不需要**——樹莓派在 12:01 重新開機過（`uptime` 只有 7 分鐘、主程式 PID 902 是開機
時就起來的），而新檔案是 11:24 傳上去的，**開機時 systemd 就已經載入新版程式碼了**。

用 sha256 逐檔比對本機 `src/` 跟樹莓派 `~/` 的五個檔案（`karaoke.py`、`line_control.py`、
`radio_pool.py`、`song_stats.py`、`weather.py`），全部 MATCH，確認部署內容正確。

**教訓**：判斷「服務有沒有吃到新程式碼」不要只看交接文件寫什麼，比對
`systemctl show -p ActiveEnterTimestamp` 跟檔案 mtime 才準——中間如果有重開機，
待辦事項可能已經被動完成了。

## ⚠ 真正的問題：ngrok 固定網域被 Mac 搶走，LINE 訊息根本沒送到樹莓派

`ngrok-tunnel.service` 狀態是 `activating (auto-restart)`、**已經失敗重試 145 次**，
log 全是坑 #2 / #12 的 `ERR_NGROK_334 endpoint already online`。

但詭異的是外網打 `https://hurling-narrow-expend.ngrok-free.dev/karaoke` 卻回 200——
一開始差點誤判成「還是正常的」。**實際抓內容才發現回來的是 OpenClaw Control 的
HTML，不是點歌系統的頁面**：

    公開網址 /karaoke  -> <title>OpenClaw Control</title>     ← 錯的
    樹莓派本機 /karaoke -> <title>🎤 點歌系統</title>          ← 對的

根因：Mac 上的 `~/Library/LaunchAgents/local.ngrok.plist`（`ngrok http 18789`，
轉發給 openclaw）**又被重新載入了**（七月份明明已經 unload 過，見坑 #2；plist 一直
沒刪，`RunAtLoad` + `KeepAlive`，Mac 只要重開機就會自己回來）。它雖然沒指定
`--url=`，但免費帳號只有一個固定網域，ngrok 會自動把那個網域配給它，等於把樹莓派
的網域整個接管走。

**結果就是：LINE 使用者傳的訊息全部送到 openclaw，樹莓派完全收不到。**

### 修法

跟使用者確認過後（改動 Mac 上的服務，比照坑 #8 的規矩先問過才動手）：

    launchctl unload ~/Library/LaunchAgents/local.ngrok.plist

**不需要 sudo、也不需要手動重啟樹莓派的服務**——`ngrok-tunnel.service` 本來就設了
`Restart=on-failure` 一直在重試，網域一放開，20 秒內自己就接手了：

    ActiveState=active  SubState=running
    tunnels: ['https://hurling-narrow-expend.ngrok-free.dev']

先確認過**樹莓派的 NLU / 語音辨識走的是區網**（`nlu_base_url` 跟 `stt_base_url` 都是
`lpldeMac-mini-2.local`，不經過這條隧道），所以關掉 Mac 這條不會影響口語理解跟語音
點歌，才動手的。

### ⚠ 這件事會再發生

`local.ngrok.plist` **還留在 `~/Library/LaunchAgents/`**，`launchctl unload` 只在這次
登入階段有效。**Mac 下次重開機/重新登入，它就會自己回來、再把網域搶走一次。**
要根治的話得把 plist 改名或移走（例如加 `.disabled` 後綴），但那會讓 openclaw 永遠
沒有公開隧道——目前看起來沒有任何東西需要它，不過這是使用者要決定的，沒有自作主張。

**以後只要「LINE 機器人突然沒反應」，第一個檢查這個**：

    curl -s https://hurling-narrow-expend.ngrok-free.dev/karaoke | head -c 100

回來的是 `🎤 點歌系統` 就正常；是 `OpenClaw Control` 就是又被搶走了。
**只看 HTTP 狀態碼會被騙**（兩邊都回 200），一定要看內容。

## 三個功能的實測結果

### ✅ 1. 天氣

樹莓派上直接跑 `weather.report()`，以及走 `handle_command('天氣')`／`('氣溫')` 都正常：

    🌤 新北市三重　毛毛雨　目前 27°C（體感 35°C）
    濕度 98%　今日 25~32°C　降雨機率 100%

### ✅ 2. 熱門電台不重複（本次最重要的需求）

在樹莓派上連抓 **70 首**（超過使用者要求的 4 小時 ≈ 60 首）：

    第  10 首  不重複  10  重複 0  池子  41
    第  40 首  不重複  40  重複 0  池子  41
    第  50 首  不重複  50  重複 0  池子 101   ← 池子快見底時自動補
    第  70 首  不重複  70  重複 0  池子 101

    總結: 70 首, 不重複 70, 重複 0

**池子見底會自動補**：跑到第 40 幾首時池子只剩幾首，`pick()` 裡的同步 `_extend()`
補了一批，池子從 41 長到 101，完全沒有中斷或重複。

也走正式服務實際測過：`POST /api/karaoke/radio` 開電台 → 切歌 → 電台自動接手，
播出的是「Jackson Wang 王嘉爾 ╳ Mayday Ashin [ Alive ]」——**不在寫死的
`POPULAR_SONGS` 12 首清單裡**，證明真的是從動態池來的，不是備援清單。

### ✅ 3. 常點歌曲資料庫

完整跑過一輪「真的播一首 → 進資料庫 → 指令查得到」：

1. `POST /api/karaoke/add` 點播「稻香」，確認 `time_pos` 真的在跑（有播出來）
2. 查資料庫：`{'n': 1, 'songs': 1, 'people': 1}`，記到了
3. `handle_command('熱門排行')` 正確列出來、附「回覆數字 1~5 直接點播」

**電台的歌確實沒被記進去**：電台播了一首之後再查，資料庫還是 `n=1` 沒變，
確認 `_record_history()` 裡 `startswith('🔀')` 的過濾有生效。

⚠ **測試過程中我自己踩的坑**：一開始直接呼叫 `song_stats.record()` 傳一個 `🔀` 開頭
的 requester，結果它照樣寫進去，差點誤判成 bug。**過濾邏輯不在 `record()` 裡面，
在呼叫端 `karaoke._record_history()`**（`record()` 的 docstring 也明講「電台自動播的
不要呼叫這支」）。以後要驗證這個行為，要測 `_record_history()` 那一層，不是 `record()`。

## 測試留下的東西

- 正式的 `~/karaoke_stats.sqlite` 裡有一筆我測試用的紀錄：requester 是 **`部署測試`**、
  歌是周杰倫〈稻香〉。留著不影響功能（之後真實使用的資料會蓋過它），要刪的話：

      ssh lpl1103@192.168.0.17 "python3 -c \"import sqlite3;c=sqlite3.connect('/home/lpl1103/karaoke_stats.sqlite');c.execute(\\\"delete from plays where requester='部署測試'\\\");c.commit()\""

- 測完已經把電台停掉、佇列清空（`radio_category: None`、`now_playing: None`、`queue: []`），
  沒有留音樂在播。

## 測試小技巧：不搶 GPIO 也能測 handle_command()

想在樹莓派上直接測 `handle_command()`，但 `line_control` 一 import 就會去抓 GPIO，
跟正在跑的服務衝突（會噴 `lgpio.error: GPIO not allocated`）。解法是 import 前先擋掉
`RPi`，讓 `pi3_control.py` 走它自己的 `MockGPIO` 分支：

    import sys; sys.modules['RPi'] = None
    import line_control as lc
    print(lc.handle_command('天氣', base_url='https://example.dev', user_id='Utest...'))

正式服務完全不受影響（照樣在跑），只是這個測試 process 自己用假的 GPIO。

---

# 2026-08-11（續）：修好 openclaw + LM Studio 本地模型（LINE bot 的 LLM 能力）

使用者澄清：LINE bot 跟 openclaw 本來就該共存——LINE bot 負責點歌邏輯，openclaw 接
本地模型（LM Studio 的 qwen3）提供「聽得懂口語」的能力。這個架構七月就建好了
（`nlu.py` + `karaoke-nlu` agent），但搬辦公室之後整條鏈路是斷的。修好了，全部實測通過。

**先澄清一個誤會**：上一節停掉 Mac 的 `local.ngrok` **沒有**影響 openclaw 本身。
openclaw 還是在 18789 正常跑，樹莓派是走**區網**呼叫它（不經過那條隧道）。
被停掉的只是 openclaw 的「對外公開隧道」，點歌系統用不到。

## 斷在哪：一共三個獨立的問題疊在一起

### 1. Mac 的主機名稱變了

`lpldeMac-mini-2` -> **`lpldeMac-mini-4`**（macOS 在新網路遇到名稱衝突會自動加編號）。
樹莓派設定檔還指向舊名稱，`curl` 舊名稱回 HTTP 000。

改 `~/pi3_line_config.json` 的 `nlu_base_url` / `stt_base_url` 成新名稱（有先備份）。

⚠ **這個名稱之後還可能再變**（每換一次網路就可能 +1）。以後 NLU 突然失效，
第一個就查這個：`scutil --get LocalHostName`，然後比對 Pi 設定檔。

### 2. ollama 死了，而 openclaw 的預設模型指向它

這是最關鍵、也最難看出來的一個。症狀是打 `openclaw/karaoke-nlu` 一律回
`upstream provider timeout`，而且**只花 1.5 秒**——快得不像 timeout。

看 gateway log 才發現真相：請求根本沒去 LM Studio，而是去了
`provider=ollama model=llama3.2:3b url=http://localhost:11434`。而 **ollama 已經沒在跑了**
（Mac 重開機後沒自動啟動）。整個 log 裡 `provider=lmstudio` 出現次數是 **0**——
代表 openclaw 從頭到尾沒真的用過 LM Studio。

原因：`agents.defaults.model.primary` 還是 `ollama/llama3.2:3b`。
雖然 `karaoke-nlu` agent 自己有 `model: lmstudio/qwen/qwen3-8b`，實際跑的時候仍然
走了 defaults。

**修法**：把 `agents.defaults.model.primary` 直接改成 `lmstudio/qwen/qwen3-8b`。
這正好也是使用者要的（讓 openclaw 用 LM Studio 的 qwen3），順便擺脫對 ollama 的依賴。

**教訓**：`upstream provider timeout` 不一定是「太慢」，也可能是**打到了錯的 provider**。
一定要看 gateway log 的 `[model-fetch] start provider=...` 那行確認實際打去哪，
不要只看錯誤訊息猜。

### 3. qwen3 是 reasoning 模型，thinking 會拖垮回應時間

修好前兩項之後可以動了，但**一次要 27.8 秒**（`reasoning_tokens: 311`）——
`nlu.py` 的 timeout 只有 8 秒，必定失敗。

openclaw 的 `chat_template_kwargs: {enable_thinking: false}` 在這條路徑上**沒有生效**
（設了還是照樣 thinking）。有效的是 qwen3 原生的 **`/no_think` 前綴**：

    有 thinking：27.8 秒（reasoning_tokens 311）
    加 /no_think： 2.8 秒（reasoning_tokens 1）

`nlu.py` 改成在使用者訊息前面自動加 `/no_think `，並把 timeout 從 8 秒放寬到 **25 秒**
（平常約 2~5 秒就回來；但如果 LM Studio 把模型從記憶體卸載了，重新載入要約 19 秒，
timeout 太短第一個使用者一定失敗）。也加了 `<think>` 區塊的過濾當保險。

另外在 openclaw 設了 `models.providers.lmstudio.timeoutSeconds: 300`
（官方文件就是建議「slow local models」這樣設）。

## 順手補的：讓 NLU 認得今天新增的三個指令

`nlu.py` 的 SYSTEM_PROMPT 原本只列舊指令，所以「今天天氣如何」會被判無法辨識。
把 `常點` / `熱門排行` / `天氣` 加進合法指令清單跟範例。

⚠ 加完第一次測試時「我最常點哪些歌」被翻成 **`點歌 常點`**（多了前綴，會變成去
YouTube 搜尋「常點」這首歌）。在 prompt 裡明確加一條規則才修好：
「常點/熱門排行/天氣/切歌/停止是完整指令，前面絕對不可以加『點歌』兩個字」。

## 實測結果（都是在樹莓派上跑真的 qwen3）

    '我想聽周杰倫的稻香'  -> '點歌 周杰倫 稻香'  (4.7s)
    '可以跳過這首嗎'      -> '切歌'             (2.1s)
    '先暫停一下音樂'      -> '停止'             (2.1s)
    '有沒有推薦五月天的歌' -> '推薦 五月天'       (2.3s)
    '放一些韓文歌來聽'    -> '熱門 kpop'        (2.1s)
    '今天天氣如何'        -> '天氣'
    '外面會不會下雨'      -> '天氣'
    '我最常點哪些歌'      -> '常點'
    '我常點什麼'          -> '常點'
    '大家最愛點什麼歌'    -> '熱門排行'
    '你叫什麼名字'        -> None（正確地不亂猜）

**九項全對**，比七月份那次的七成準確率好很多（`/no_think` 讓輸出乾淨很多是主因）。

端對端也用真實簽章的 LINE webhook 從公開網址測過：送「我想聽五月天的溫柔」，
gateway log 出現 `provider=lmstudio model=qwen/qwen3-8b status=200`，
樹莓派真的開始播〈溫柔〉。

## ⚠ 重啟服務的替代方法（不用 sudo 密碼）

這台 sudo 要密碼，照坑 #10 不代替使用者輸入。但 `line-control.service` 是用
`User=lpl1103` 跑的，所以可以自己送訊號讓 systemd 重啟：

    kill -9 $(pgrep -f 'python3 /home/lpl1103/line_control.py')

**一定要用 `-9`（SIGKILL）**：systemd 的 `Restart=on-failure` 把 SIGTERM 當成「正常結束」
不會重啟，SIGKILL 才算失敗會觸發重啟。送出後約 5~10 秒服務自己回來。
**動之前先確認沒有音樂在播**（`pgrep mpv`），不然 mpv 會變成孤兒程序。

## 現在的完整架構

    LINE 使用者口語
      -> ngrok(hurling-narrow-expend) -> 樹莓派 192.168.0.17:8000
      -> handle_command() 既有規則比對（點歌/切歌/天氣/常點...）
      -> 都比對不到 -> nlu.py -> http://lpldeMac-mini-4.local:18789/v1/chat/completions
                                  (model=openclaw/karaoke-nlu, 前綴 /no_think)
      -> openclaw karaoke-nlu agent -> LM Studio http://localhost:1234 -> qwen3-8b
      -> 翻成一行指令 -> 遞迴丟回 handle_command() 執行
      -> 還是不認得 -> 回「不認識的指令」（跟以前一樣，不會誤觸發）

語音點歌另外走 `stt.py` -> Mac 的 whisper server (8765)，同樣已更新成新主機名稱。

---

# 2026-08-11（續二）：USB 麥克風語音控制（喚醒詞「小P」）

使用者要「像智慧音響那樣」用麥克風語音控制點歌系統，喚醒詞定為「小P」。

## 硬體：WM8960 板上的麥克風是壞的，改用 USB 麥克風

先試了樹莓派上原有的 WM8960 音效板（`arecord -l` 有列出 capture 裝置），
**錄到的是精準的振幅 0**——連環境底噪、電路底噪都沒有。測過：
- 三種裝置路徑（`hw:0,0` / `plughw:0,0` / `default`）
- 兩種取樣率（16k / 48k）
- 三條輸入線路（LINPUT1 / LINPUT2 / LINPUT3，把 2/3 的增益從 0 拉滿也試過）

全部都是 0。增益設定本身是對的（LINPUT1 滿檔 29dB、Capture 開著 12dB），
所以不是設定問題，是**訊號根本沒進到 ADC**。測完已把改動的 mixer 還原。
結論：**這片板子的麥克風不能用，不要再花時間**。

改插 USB 麥克風（C-Media / TI PCM2902，`lsusb` 顯示 `08bb:2902`）：
- 掛在 **card 4**，裝置字串 `plughw:4,0`
- ⚠ **`arecord -l` 裡它的短名稱是 `Device`**，完全看不出是麥克風。
  第一版偵測程式用 `\S+` 只抓短名稱去比對 "usb"，結果漏掉它、退回去用沒作用的
  WM8960。**要比對整行**（整行才有 `[USB PnP Sound Device]`）。

### USB 麥克風增益要調，預設是 0

插上去預設 `Mic` 增益是 **0（0%）**，錄到的等於只有殘餘噪音，
Whisper 會吐出 `Every remark remark remark` 這種英文亂碼。

調整過程（這支麥克風的甜蜜點）：
- 增益 0 → 振幅 2497（太小，辨識失敗）
- 增益 14 + AGC 開 → 振幅 32767 **削波失真**，辨識更糟（`And the mast mast mast`）
- **增益 8、AGC 關 → 振幅 8407（26% 滿刻度），辨識成功** ✅

    amixer -c 4 sset 'Auto Gain Control' off
    amixer -c 4 sset Mic 8 unmute

⚠ ALSA 設定重開機不會保留（見前面 WM8960 的坑），之後如果語音突然失效，
先查 `amixer -c 4 sget Mic` 是不是又變回 0。

## whisper server 加了語言鎖定 + 領域提示

`~/.whisper_server/whisper_server.py` 原本沒指定語言，收音稍差就猜成英文吐亂碼。
加了兩個參數：
- `language='zh'` —— 這系統只講中文，直接鎖定
- `initial_prompt` —— 塞入喚醒詞、指令詞、常見歌手/歌名，
  讓它對專有名詞優先往這些詞去對

實測同一段音檔：改之前 `小屁 我想聽到響`，改之後 `小P、我想聽到聲音。`
（喚醒詞從「小屁」變成正確的「小P」）。

## voice_control.py（新檔，樹莓派 systemd 服務）

    arecord 持續錄音 -> 純 Python 算 RMS 做 VAD
    -> 講完一句丟給 Mac 的 whisper -> 轉成文字
    -> 文字裡有喚醒詞才處理（沒有就丟掉，這是擋掉喇叭音樂的關鍵）
    -> 剝掉喚醒詞，POST 給 line_control 的 /api/voice 執行

**刻意不裝 numpy / pyaudio / sounddevice**：這台是最小化安裝，
而且 Python 3.13 已經把 `audioop` 移除了。RMS 用 `struct` + 純 Python 算，
一次只算 0.1 秒（1600 點），效能綽綽有餘。

### 踩到的三個坑（都已修）

1. **`overrun!!! (at least 23446 ms long)`**
   辨識+執行指令要 20 秒以上，原本在主迴圈裡同步做，那段期間沒人讀 arecord 的輸出，
   緩衝區溢位、使用者講的話全丟。**改成背景執行緒 + queue**，錄音迴圈永不阻塞。

2. **噪音尖峰誤觸發 -> Whisper 幻覺**
   這支麥克風底噪高（RMS≈1850）且會突然衝到 2700+。原本門檻 `底噪+500` 太近，
   一直被噪音觸發、錄到 1.4 秒純雜訊，Whisper 就吐出重複迴圈幻覺：
   `比例比例比例…`、`南、南、南…`、`張張張張…`
   修法有三層：
   - 門檻改成 `max(底噪×1.5, 底噪+900)`
   - **要連續 3 個 chunk（0.3 秒）都超過門檻**才算人聲，單一尖峰不理會
   - 加 `looks_hallucinated()` 過濾重複輸出（同一字元佔比 >50%、
     或不重複字元佔比 <25% 就丟掉）。有寫單元測試，3 個真實幻覺樣本全擋、
     5 個正常指令全放行。

3. **句子被切太早**
   原本 `SILENCE_HOLD_SEC=0.8`，訊噪比差時句中換氣就被判定講完，
   「小P我想聽稻香」只錄到 1.9 秒、歌名被截斷。改成 **1.2 秒**後錄到 4.7 秒，正常。

## line_control.py 新增 /api/voice

給語音守護程式用的入口，**只收已經去掉喚醒詞的純指令文字**，
然後丟進跟 LINE 完全一樣的 `handle_command()`——語音跟打字走同一條路，
不會有兩套行為。**只允許 127.0.0.1 呼叫**（外部回 403，已實測），
避免區網上任何人都能對麥克風端點下指令。

## NLU 加了同音字修正

語音辨識最大的問題是同音字：稻香 -> 道香/到響/到聲/到像。
在 `nlu.py` 的 system prompt 加了「使用者的話可能是語音辨識轉來的，
有同音字錯誤請自動更正成正確歌名」，並列了對照範例。

實測**有講歌手時很準**（`我想聽周杰倫的告白汽球` -> `點歌 周杰倫 告白氣球` ✅），
**只講歌名時大約一半機率**（`道香` 有時修正成 `稻香`、有時原樣輸出）。
→ **給使用者的建議：講歌名時盡量帶上歌手名。**

## ⚠ LM Studio 會塞車，不要連發請求

測試時連續打了 6 個請求，每個樹莓派端 25 秒逾時放棄，
但 **LM Studio 那邊還在繼續算**，請求一路堆積，狀態卡在 `PROCESSINGPROMPT`，
之後連最簡單的直接呼叫都要 **63 秒**。

等它消化完（`lms ps` 回到 `IDLE`）再測，延遲就回到正常的 **3~8 秒**。
真實使用是一個人偶爾講一句，不會觸發這個問題，但**寫測試腳本時每次之間要留間隔**。

## 現在的服務清單（樹莓派）

| 服務 | 用途 | 開機自啟 |
|---|---|---|
| `line-control` | LINE 機器人 + 點歌系統 + 網頁 | ✅ |
| `ngrok-tunnel` | 對外隧道 | ✅ |
| `voice-control` | 麥克風語音控制（新增） | ✅ |

## sudo 已改成免密碼（限縮範圍）

使用者自己執行了設定，`/etc/sudoers.d/lpl1103-nopasswd` 只開放
`systemctl` / `apt-get` / `apt` 三個指令，不是全開。
所以現在可以直接 `sudo -n systemctl restart xxx`，不用再請使用者代跑。

## 重新設計：麥克風實體開關 = 說話按鈕（取代 VAD）

原本用音量偵測（VAD）猜使用者什麼時候講完，問題一堆：換氣被誤判成講完、
歌名被切掉、喇叭的音樂會誤觸發、噪音尖峰觸發後 whisper 吐幻覺。

使用者講出真正想要的流程後整個簡化了：

    打開麥克風 -> 講話 -> 關掉麥克風 -> 執行指令 -> 音樂繼續放

**關鍵**：這支麥克風的實體開關會讓整個 USB 裝置從系統消失，所以
「錄音串流中斷」就是**明確的說完訊號**，比任何音量門檻都可靠。

改完之後：
- 不再需要 VAD、靜音門檻、連續 chunk 判斷那一整套
- **喚醒詞變成可選**——打開麥克風本身就是意圖。有講「小P」就剝掉，沒講也照樣執行
- 想講多久就講多久，不會被切斷

實測流程完全正常：`🎤 麥克風已開啟` -> 錄 4.4 秒 -> `🔇 麥克風已關閉` ->
轉文字 -> 剝喚醒詞 -> 執行。

## 麥克風的自動化處理（都是實測踩出來的）

1. **USB 重新列舉會把增益歸零**：用實體開關關掉再打開，ALSA 設定全部重設，
   增益變 0 = 收不到聲音。所以每次偵測到裝置都要重設增益，不能只設一次。
2. **增益自動適應**：講話大小聲、遠近都影響音量。削波（峰值 ≥30000）會嚴重
   破壞辨識，太小聲也辨識不出來。每次錄完看峰值自動調整，存在 `~/.voice_mic_gain`。
   實測：增益 14+AGC -> 峰值 32767 削波、辨識全錯；增益 8 -> 峰值 8407 正常。
3. **絕不退回 WM8960**：偵測不到 USB 麥克風時要回報「沒有裝置」並等待，
   不能退回那片故障的板子——那樣程式看起來在跑、實際永遠聽不到聲音，更難察覺。
4. **錄音會保存**在 `~/voice_recordings/`（留最近 10 段），
   這樣調辨識參數時可以拿真實音檔反覆測試，不用每次都麻煩使用者重講。

## ⚠ 目前的瓶頸：這支 USB 麥克風訊噪比太差

分析實際錄音（`~/voice_recordings/*.wav`）發現：

    長度 0.88s  peak=4243  rms=2095
    每 0.1 秒 RMS: 2070 2066 2050 2035 2053 2111 2154 2144
    -> 估算 SNR ≈ 0.3 dB

每個 chunk 音量幾乎一模一樣、完全沒有人聲該有的起伏，
代表**那段錄音裡根本沒有有效人聲，全是底噪**。

拿同一段音檔測四種 whisper 設定（鎖中文+長提示 / 只鎖中文 / 短提示 / 完全不設），
全部都是幻覺輸出（`記得記得記得…`、`感谢观看`、`她她她她…`、`Thank you.`）。
**這證明問題不在 whisper 參數，在收音本身。**

實測辨識結果的規律：
- 峰值 8407（26% 滿刻度）-> `小P、我想聽到聲音`（部分正確，喚醒詞對）
- 峰值 32768（削波）-> `小P、我要聽到香了`（歌名全錯）
- 峰值 4243 但無人聲起伏 -> 純幻覺

**下一步該試的（依序）**：
1. **講話離麥克風近一點（5~10 公分）**——距離加倍就少 6dB，這是最有效且免費的改善
2. 如果還是不行，換一支收音品質好一點的麥克風（這支 C-Media/PCM2902 是最便宜那種）
3. whisper 參數已經確認不是瓶頸，不用再花時間調

## 結論：軟體都做完了，瓶頸是這支麥克風的收音品質

同一句「我想聽稻香」，六次嘗試被辨識成六種不同結果：

    我想聽到聲音 / 我要聽到香了 / 我想聽到香 / 我想聽到響 / 我想聽到一下 / 我想聽小聲

**每次錯得不一樣**——這不是固定的同音字（那可以用規則修），是辨識在猜。
不要再一條一條補同音字規則，那是打地鼠。

已經確認過**不是**這些原因：
- 不是 whisper 參數：同一段音檔測四種設定（鎖中文+長提示/只鎖中文/短提示/完全不設），
  輸出一模一樣的幻覺
- 不是降噪能救：頻譜相減後 SNR 只從 0.2dB 變成 0.4dB
- 不是音量沒調好：削波跟太小聲都試過，最好的一次（峰值 6150、無削波、錄滿 6 秒）
  仍然辨識錯誤
- 不是錄音被切掉：修剪從 0.35 秒降到 0.15 秒、也請使用者前後各留一秒緩衝之後，
  錄到完整 5~6 秒，還是錯

實測數據：這支 C-Media/PCM2902 的底噪恆定在 RMS≈2000（滿刻度的 6%），
人聲錄起來的高音量段大約 4000~6000，**動態範圍只有 6~7dB**。
語音辨識大致需要 15~20dB 才穩。

### 已知可用的替代方案

**LINE 語音訊息那條路是好的**——用手機麥克風收音，品質好很多，
走的是同一套 `stt.py` -> whisper -> `handle_command()`。
在換麥克風之前，語音點歌建議走 LINE 傳語音訊息。

### 如果之後要換麥克風

軟體端完全不用改，`detect_capture_device()` 會自動抓新裝置、
`configure_mic()` 會自動設增益。插上去重啟 `voice-control` 就好。

## NLU 逾時調整

實測同一句話跑 4 次，有 1 次會超過 25 秒（LM Studio 提示詞快取沒命中時要
重新處理整段長提示詞）。使用者會看到「不認識的指令」，但其實只是還沒算完。
`nlu.py` 的 `_TIMEOUT` 從 25 秒改成 **45 秒**——語音流程本來就是關麥克風後等結果，
寧可多等也不要白白失敗。

## 麥克風語音控制實測成功

實際成功的那一次：

    🎤 麥克風已開啟 -> 錄到 4.8 秒（峰值 16809，51% 滿刻度、無削波）
    聽到：'我想聽周杰倫的導向。'      <- 稻香被聽成導向
    -> 執行：'我想聽周杰倫的導向'
    <- 已加入點歌佇列：周杰倫 導向
    實際播放：周杰倫 Jay Chou【稻香 Rice Field】-Official Music Video ✅

**成功的兩個關鍵**：

1. **音量落在正確範圍**（峰值 16809 ≈ 51%）。先前一直在「爆音」跟「太小聲」之間
   擺盪，根因是把**開關的喀聲**誤判成使用者講話太大聲而一直調低增益。
   修掉邊緣修剪 + 把 QUIET_PEAK 從 4000 提高到 18000 之後才穩定。
2. **使用者講了歌手名**。「稻香」還是被聽成「導向」，但因為有「周杰倫」這個
   正確關鍵字，YouTube 搜尋「周杰倫 導向」照樣命中正確的〈稻香〉。
   **這是這支麥克風的實用解法**：子音辨識先天弱，歌手名等於多一層保險。

## ⚠ 網路排錯：先確認自己在哪個網段

有一次「樹莓派連不到、掃整個 192.168.0.x 都空的」，一度以為是樹莓派電源不穩
反覆重開機。**實際上是 Mac 自己跑到別的網段去了**：

    上層網路 192.168.1.x  <- Mac 跑到這裡
       └── ASUS rt-ax56u（在 192.168.1.101，這是它的 WAN 側）
             └── 內部網路 192.168.0.x  <- 樹莓派在這裡

Mac 在 ASUS 路由器**前面**，中間隔著 NAT，所以連不進去。
判斷方法：`route -n get default` 看閘道是不是 192.168.0.1；
`ifconfig` 看 en1（**這台 Mac 的 en1 才是 Wi-Fi，en0 是乙太網路**）。
解法是把 Mac 的 Wi-Fi 切回 ASUS 那個網路。

**教訓**：連不到裝置時，先確認自己這端的網段/閘道，不要一開始就懷疑對方的
電源或硬體——我當時已經寫了一整段「可能是供電不足導致反覆重開機」的錯誤推論。

## ngrok 網域衝突：永久解決

Mac 的 `~/Library/LaunchAgents/local.ngrok.plist` 有 `RunAtLoad` + `KeepAlive`，
**每次 Mac 重新登入就會自己回來**，把免費 ngrok 帳號那個唯一的固定網域搶走
（樹莓派端累計重試失敗 277 次），症狀是「點歌系統前端看不到了」——
打開對外網址看到的是 OpenClaw Control 的頁面。

已改名成 `local.ngrok.plist.disabled` **永久停用**，Mac 重開機也不會再回來。
要復原就把檔名改回去。

**再次澄清「能不能共存」**（使用者問過兩次）：
- **openclaw 本身 vs LINE 機器人 -> 可以共存**，現在就是這樣跑的：
  樹莓派走**區網**呼叫 openclaw 做 NLU/語音，完全不經過 ngrok
- **樹莓派的 ngrok vs Mac 的 ngrok -> 不能共存**，免費帳號只有一個固定網域

停掉 Mac 那條隧道後實測：對外網址 `/karaoke` `/display` `/manual` 全部 200，
openclaw 仍在 18789 正常運作，樹莓派連過去也是 200。兩邊都好。
