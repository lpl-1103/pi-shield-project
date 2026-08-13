# 部署

## 這個目錄是什麼

樹莓派上實際在跑的 systemd unit、設定檔範本、推送腳本。
在此之前這些東西**只存在於樹莓派上**，機器一掛就得憑記憶重建。

## 機器

| 角色 | 機器 | 位址 | 負責 |
|---|---|---|---|
| 主機 | Raspberry Pi 4 (8GB) | `raspberrypi.local` | Flask、點歌佇列、mpv 播放、語音控制 |
| 週邊 | Raspberry Pi 3 + IT Shield v3.0 | — | LED／蜂鳴器／繼電器（GPIO，目前未接） |
| 後端 | macOS | `<主機名>.local` | openclaw + LM Studio（NLU）、mlx-whisper（STT） |

**一律用 mDNS 名稱，不要寫死 IP。** 這個環境的網段換過、Mac 主機名也換過，
三次部署失敗都出在這裡。

## 換一台電腦接手：從零到跑起來

只要有這個 repo 就夠了，程式本身沒有任何寫死的本機路徑
（`src/*.py` 的路徑全部由 `__file__` 或 `~` 推出來）。

### 你需要準備的

| 東西 | 說明 |
|---|---|
| Raspberry Pi 4（或 3B+ 以上） | Raspberry Pi OS Lite 64-bit，能上網 |
| LINE Official Account | LINE Developers Console 開一個 Messaging API channel |
| ngrok 帳號 | 免費方案就夠，需要一個 static domain |
| （選配）一台 Mac | 只有「聽得懂口語」跟「語音辨識」需要，見 [`../mac-services/README.md`](../mac-services/README.md)。不裝的話系統照樣能用，只是變回只認固定指令 |
| （選配）USB 麥克風 | 麥克風語音控制用，要有實體開關 |

### 步驟

```bash
# 1. 樹莓派裝系統套件
ssh <你的帳號>@raspberrypi.local
sudo apt update && sudo apt install -y mpv
pip3 install -r requirements.txt --break-system-packages
# yt-dlp 裝官方 standalone 版（apt 那版太舊會解析失敗），ngrok 裝官方 binary

# 2. 從你的電腦推程式上去
export PI_HOST=<你的帳號>@raspberrypi.local     # deploy.sh 會讀這個
scp src/*.py $PI_HOST:~/

# 3. 設定檔
scp deploy/pi3_line_config.example.json $PI_HOST:~/pi3_line_config.json
ssh $PI_HOST 'chmod 600 ~/pi3_line_config.json'
# 上去把佔位字串換成真的值（LINE 的兩把鑰匙一定要填，NLU/STT 沒有的話設 false）

# 4. systemd
#    ⚠ 三個 .service 檔裡的使用者與路徑寫死成 lpl1103，換帳號要先改：
sed -i '' "s/lpl1103/<你的帳號>/g" deploy/*.service          # macOS
scp deploy/*.service $PI_HOST:/tmp/
ssh $PI_HOST '
  sudo cp /tmp/*.service /etc/systemd/system/ &&
  sudo systemctl daemon-reload &&
  sudo systemctl enable --now line-control ngrok-tunnel voice-control'

# 5. ngrok 網域
#    ngrok-tunnel.service 裡是佔位字串 YOUR-STATIC-DOMAIN，換成你自己的

# 6. LINE Developers Console
#    Webhook URL 設成 https://<你的網域>/callback，並開啟 Use webhook
```

### 確認成功

```bash
curl -s http://raspberrypi.local:8000/karaoke | grep -c 小樂點歌台   # > 0
curl -s http://raspberrypi.local:8000/api/karaoke/status            # 回 JSON
```

然後在 LINE 傳「點歌 小星星」，喇叭應該要出聲。

### 沒有麥克風 / 沒有 Mac 怎麼辦

- **沒有 Mac**：`pi3_line_config.json` 把 `nlu_enabled` 跟 `stt_enabled` 設成 `false`。
  固定格式指令（點歌／切歌／熱門…）全部照常
- **沒有 USB 麥克風**：不要 enable `voice-control.service` 就好，其他不受影響

## 日常更新

```bash
deploy/deploy.sh            # 推全部並重啟，最後會驗證頁面內容
deploy/deploy.sh --check    # 只比對差異
```

## 開機自動啟動

三個服務都 `enable` 了，斷電重開不用手動介入。
另外設了 tty1 自動登入（`/etc/systemd/system/getty@tty1.service.d/autologin.conf`），
這樣 `/display` 大螢幕那條不用有人去打密碼。

## 群組行為的回歸測試

`deploy/test_group_gate.py` 對**真正在跑的服務**送簽章正確的假 webhook，
驗證群組閘門（有無喚醒詞、@全體成員、單字元指令、一對一不受影響共 8 種情境）。

```bash
scp deploy/test_group_gate.py $PI_HOST:/tmp/ && ssh $PI_HOST 'python3 /tmp/test_group_gate.py'
```

用「排隊」當測試指令（唯讀，不會真的點歌）。判斷「有沒有回覆」是撈 journal 裡
`line_reply` 對假 replyToken 失敗時印的那行——**所以 unit 一定要有
`Environment=PYTHONUNBUFFERED=1`**，否則 print 會被緩衝，測試會全部誤判成「沒回覆」。

## 驗證部署有沒有真的成功

**只看 HTTP 狀態碼會被騙。** ngrok 網域被別台機器搶走時，公開網址一樣回 200，
只是內容變成別的服務。`deploy.sh` 因此會另外檢查回傳內容裡有沒有「小樂點歌台」。

```bash
curl -s http://raspberrypi.local:8000/karaoke | grep -c 小樂點歌台   # 應該 > 0
curl -s http://raspberrypi.local:8000/api/karaoke/status | python3 -m json.tool
```
