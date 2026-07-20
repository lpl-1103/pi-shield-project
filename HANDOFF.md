# 交接文件 — Pi3 Shield 控制專案

最後更新：2026-07-16（收工時樹莓派已關機，所有服務目前**沒有**在跑）

## 我們在做什麼

把樹莓派上的 ITtraining Pi I/O Shield v3.0（2 顆燈泡 LED1/LED2、1 個蜂鳴器、1 個繼電器）做成可以簡單操作的專案，操作方式從「終端機按鍵」一路擴充到「LINE 聊天室文字指令」再到「LINE 裡點連結打開的圖形化網頁面板」。

樹莓派資訊：
- SSH: `ssh lpl_1103@192.168.1.53`，密碼見私人筆記（公開版不記錄實際密碼）（使用者名稱是 `lpl_1103`，主機名稱是 `LPL`，不要搞混）
- 硬體：Raspberry Pi 3 Model B，OS 是 Debian Trixie (13) aarch64

## 已經完成什麼

1. **[pi3_control.py](pi3_control.py)**（本地 + 已上傳到樹莓派 `~/pi3_control.py`）
   核心 `Pi3Shield` 類別（LED 長亮/閃爍/關、蜂鳴器 PWM 音符+旋律播放、繼電器開關），以及一個獨立可跑的終端機按鍵互動介面（raw tty 模式，仿照樹莓派上原本的 `~/it_shield_led_keyboard.py`）。
   - LED：`1`/`2`/`3` 長亮（單1/單2/一起），`4`/`5`/`6` 閃爍（單1/單2/一起），`0` 全關。每個指令都是設定「兩顆燈泡的完整狀態」，沒提到的燈泡會自動關閉。
   - 蜂鳴器：`q w e r t` = do re mi fa so，`p` = 播放《粉刷匠》（旋律用使用者提供的簡譜 `PAINTER_SONG_JIANPU` 生成，可直接改那個字串調旋律）。
   - 繼電器：`o` 開 `k` 關。
   - 已拿掉原本的「漸變/pulse」LED 模式（照需求砍掉）。

2. **[line_control.py](line_control.py)**（本地 + 已上傳到樹莓派 `~/line_control.py`）
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

4. **YouTube 音樂播放**（[line_control.py](line_control.py) + [karaoke.py](karaoke.py)）：裝了 `mpv`、`yt-dlp`（升級成 GitHub 最新 standalone 版，蓋掉太舊的 apt 版本）、`deno`（yt-dlp 做 YouTube 簽章解析需要的 JS runtime，沒裝的話很容易解析失敗）。

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
