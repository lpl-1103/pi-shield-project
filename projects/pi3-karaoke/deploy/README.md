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

## 第一次安裝

```bash
# 1. 系統套件
sudo apt install -y mpv
pip3 install -r ../requirements.txt --break-system-packages
# yt-dlp 與 ngrok 裝官方 binary 到 /usr/local/bin

# 2. 程式
scp ../src/*.py lpl1103@raspberrypi.local:~/

# 3. 設定檔（chmod 600，不進 git）
scp pi3_line_config.example.json lpl1103@raspberrypi.local:~/pi3_line_config.json
# 上去把佔位字串換成真的值

# 4. systemd
scp *.service lpl1103@raspberrypi.local:/tmp/
ssh lpl1103@raspberrypi.local '
  sudo cp /tmp/*.service /etc/systemd/system/ &&
  sudo systemctl daemon-reload &&
  sudo systemctl enable --now line-control ngrok-tunnel voice-control'
```

`ngrok-tunnel.service` 裡的網域是佔位字串，要換成自己的 ngrok static domain。

## 日常更新

```bash
deploy/deploy.sh            # 推全部並重啟，最後會驗證頁面內容
deploy/deploy.sh --check    # 只比對差異
```

## 開機自動啟動

三個服務都 `enable` 了，斷電重開不用手動介入。
另外設了 tty1 自動登入（`/etc/systemd/system/getty@tty1.service.d/autologin.conf`），
這樣 `/display` 大螢幕那條不用有人去打密碼。

## 驗證部署有沒有真的成功

**只看 HTTP 狀態碼會被騙。** ngrok 網域被別台機器搶走時，公開網址一樣回 200，
只是內容變成別的服務。`deploy.sh` 因此會另外檢查回傳內容裡有沒有「小樂點歌台」。

```bash
curl -s http://raspberrypi.local:8000/karaoke | grep -c 小樂點歌台   # 應該 > 0
curl -s http://raspberrypi.local:8000/api/karaoke/status | python3 -m json.tool
```
