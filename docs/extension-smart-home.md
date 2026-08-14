# 擴展方向：智慧家庭

> **這份文件不屬於點歌台的核心功能。**
>
> 點歌台交接出去時，這裡描述的是「這個系統之後可以往哪裡長」，
> 而不是「接手的人必須維護什麼」。核心系統（點歌、語音、LINE Bot）
> 不依賴這裡的任何東西，全部拿掉也照常運作。
>
> **唯一已經上線並成為核心功能的是「LINE 控制電風扇」**
> ——那部分寫在 [`HANDOFF.md`](HANDOFF.md) §15、§17，不在這裡。
>
> ⚠ 2026-08-14 起，Home Assistant 相關的後續進度**不再更新到這個 repo**，
> 改為本機記錄。這份文件保留到目前為止的架構決定與踩坑記錄。

## 這條線目前走到哪

```
✅ 已上線   LINE 指令 → 樹莓派 → 博聯小黑豆 → 紅外 → 電風扇
                （開/關/高/中/低/擺頭，實機驗證通過）

🔵 進行中   第二台樹莓派跑 HA OS，管 Zigbee 裝置與其他家電
                （卡在電壓不足，見下）

❌ 已排除   透過 Aqara M3 中樞轉發
                （M3 不開放本機介面，實測確認）
```

---

## 目標架構

```
┌── 樹莓派 4「點歌台」＝ 主控 ────────────────┐
│  LINE Bot（使用者唯一入口）                  │
│  點歌系統 / 語音辨識 / 自然語言理解           │
│  ir_remote.py → 博聯小黑豆（紅外）           │
└────────────────┬────────────────────────────┘
                 │ HTTP：HA REST API + 長期權杖
                 ▼
┌── 樹莓派「HA OS」＝ 家電管理 ────────────────┐
│  Home Assistant                             │
│   ├ Mosquitto（MQTT broker）                │
│   ├ zigbee2mqtt ← USB Zigbee 接收器          │
│   │    ├ Aqara D1 無線開關                   │
│   │    └ Zigbee 繼電器（待購）                │
│   └ iRobot 掃地機器人整合（之後）             │
└─────────────────────────────────────────────┘
```

**分工原則**：使用者只跟 LINE 說話 → 點歌台負責理解意圖 → 家電相關的轉給 HA 執行。
HA 不直接面對使用者，它是被呼叫的執行層。

## 為什麼這樣分

| | 點歌台 | HA OS |
|---|---|---|
| 角色 | 對外入口、意圖理解 | 家電執行層 |
| 對外 | LINE Webhook（ngrok） | 不對外，只在區網 |
| 系統 | Raspberry Pi OS，跑多個服務 | **HA OS 是整台專用**，不能兼跑別的 |
| 掛掉的影響 | 點歌與 LINE 全失效 | 家電失效，點歌不受影響 |

HA OS 是完整作業系統映像，**那台 Pi 不能再跑其他東西**——這是選 HA OS 的代價，
換來的是 Supervisor、附加元件商店、備份還原都是現成的。

## 必買清單

| 品項 | 用途 | 備註 |
|---|---|---|
| **Zigbee USB 接收器** | zigbee2mqtt 的必要硬體 | 樹莓派沒有 Zigbee 天線。常見選擇 Sonoff ZBDongle-E / ConBee II |
| **USB 延長線** | 把接收器拉離樹莓派 | **不是可有可無**，見下方干擾說明 |
| **USB SSD 或高耐寫 SD 卡** | HA 的儲存 | HA 的 recorder 寫入量極大，一般 SD 卡容易寫壞 |
| Zigbee 繼電器 | 控制電燈等 | 使用者已規劃 |

## ⚠ 規劃階段就要知道的四件事

### 1. Zigbee 跟 Wi-Fi 都在 2.4GHz，會互相干擾

而且 **USB 3.0 介面本身就是 2.4GHz 干擾源**。Zigbee 接收器直接插在樹莓派上，
實測常見的症狀是「裝置隨機離線、指令偶爾沒反應」，很難查。

**做法**：一定要用 USB 延長線把接收器拉離主機 30 公分以上，
並盡量遠離 Wi-Fi 天線與 USB 3.0 裝置。

另外 Zigbee 頻道要跟 Wi-Fi 錯開（Wi-Fi 目前在 `Golden-IC`，
樹莓派連的是 5GHz，但家中 2.4GHz 頻道仍需確認）。

### 2. D1 按鈕只能屬於一個 Zigbee 網路

移到 zigbee2mqtt **必須先從 M3 移除**，兩邊不能並存。
移除後 Aqara App 裡所有跟 D1 有關的自動化都會失效。

**建議順序**：先把 zigbee2mqtt 跑起來、確認能收到別的裝置，
再把 D1 從 M3 移除並重新配對。不要先拆再建。

### 3. M3 的處置：✅ 已決定放棄

D1 移走之後 M3 沒有子裝置，而樹莓派控制不了它（HANDOFF §14、§16 實測），
剩下的內建紅外也被小黑豆覆蓋。**使用者決定直接不用。**

實務上的意思：

- 不再需要維護 Aqara App 那條路，家電控制全部收斂到 HA
- `src/aqara_hub.py`、`deploy/aqara_discover.py` 這兩支**對本專案已無用途**，
  但保留在 repo 裡——它們是「舊款 Aqara/小米中樞區網協定」的完整實作，
  之後若接觸到 M2 之類支援該協定的硬體可以直接拿來用
- 若哪天想要「兩台 Pi 都掛掉時仍能用手機控制家電」的備援，
  M3 是現成的選項，屆時再重新啟用即可（它本身沒壞，只是不納入這套架構）

### 4. 紅外要不要搬到 HA

目前紅外在**點歌台**上（`ir_remote.py` + 小黑豆，已驗證可用）。

| | 留在點歌台 | 搬到 HA |
|---|---|---|
| 現在能用嗎 | ✅ 已驗證 | 要重做 |
| 符合分工原則 | ❌ 家電邏輯跑在主控上 | ✅ |
| 紅外碼 | 已學好在 `~/ir_codes.json` | HA 的 Broadlink 整合要重新學或匯入 |

**建議：先不要搬。** 它現在能用，搬動有風險而收益只是「架構比較整齊」。
等 HA 那邊穩定、且真的有需要（例如要跟 Zigbee 繼電器做連動）再說。

## 兩台 Pi 怎麼溝通

**HA REST API + 長期存取權杖**，點歌台當客戶端：

```
LINE「開客廳燈」
  → 點歌台 handle_command()
  → 比對不到既有指令 → nlu.py 翻譯成家電指令
  → 呼叫 HA REST API（POST /api/services/switch/turn_on）
  → HA 透過 zigbee2mqtt 開繼電器
```

為什麼不用 MQTT 直連：點歌台只需要「下指令」，不需要訂閱狀態，
REST 比較單純、也不用在點歌台上再裝一個 MQTT 客戶端。
之後若需要「HA 狀態變化要通知點歌台」再考慮 MQTT。

**權杖要跟 LINE 密鑰同等看待**——放 `pi3_line_config.json`、不進 git。

## 建議的推進順序

1. **HA OS 裝起來**（用 SSD，不要 SD 卡），確認能開網頁介面
2. **Zigbee 接收器插上**（記得用延長線），裝 Mosquitto + zigbee2mqtt 附加元件
3. **先配對一個不重要的裝置**確認整條鏈路通
4. **D1 從 M3 移除 → 配對到 zigbee2mqtt**，驗證按鍵事件收得到
5. **在 HA 裡做第一條自動化**：D1 按鍵 → 目前能控的東西
6. **點歌台接上 HA REST API**，讓 LINE 也能觸發
7. 繼電器到貨後接入
8. iRobot 之後再加

每一步都要能單獨驗證再往下，不要一次全部接起來——
出問題時無從判斷是哪一段。

## HA OS 安裝進度（2026-08-14）

### 已完成

| 項目 | 狀態 |
|---|---|
| 硬體 | Raspberry Pi 4 Model B（另一台，跟點歌台同型號） |
| 系統 | HA OS 18.2（rpi4-64），燒在 32GB SD 卡 |
| 網路 | Wi-Fi 連上 `Golden-IC`，取得 `192.168.0.6` |
| 帳號 | 已建立 |
| 存取權杖 | 已產生（放樹莓派設定檔，不進 git） |

### 🔴 卡住的問題：電壓不足

**HA 自己的「Raspberry Pi 電源供應檢查工具」回報「偵測到電壓不足」，標記為「關鍵」等級。**

症狀是 **8123 埠時通時不通**——機器 ping 得到（核心活著、網路正常），
但 HA 的服務層整個沒起來。Pi 4 在低電壓下不會直接關機，
而是降頻、USB 供電不穩、容器崩潰，剛好就是這個表現。

**繼續往下裝 zigbee2mqtt 之前必須先解決。** 理由：

- Zigbee 接收器是 USB 裝置，**最先受害**
- 在不穩的基礎上疊東西，出問題會分不清是設定錯還是電不夠
- **低電壓下的寫入會慢慢損毀 SD 卡**，HA 的寫入量又特別大

需要 **5V / 3A（15W）USB-C**。三個坑：PD/QC 快充頭若不支援 5V/3A 檔位只會給到 2A；
細長線材本身會壓降；共用延長線插太多東西時電壓會被拉低。

### ⚠ 判斷電源要看 HA 的回報，不要只看紅燈

排查過程中一度看紅燈判斷：「紅燈恆亮 → 不是電源問題」，**這個判斷是錯的**。

紅燈只在電壓低於 4.63V 的**當下**閃爍，看的那一瞬間正常不代表沒發生過。
**HA 內建的電源檢查工具是持續監測並記錄的**，它抓到了 55 分鐘前的事件。

教訓：有持續監測的工具時，不要用瞬時的目視觀察去否定它。

### ⚠ Wi-Fi 設定碟的正確路徑（我第一次放錯）

HA OS 讀設定碟的結構是：

    USB 卷標必須是 CONFIG（全大寫）
    └── network/          ← 直接在根目錄
        └── my-network    ← 無副檔名，必須 LF 換行

**我第一次做成 `CONFIG碟/CONFIG/network/my-network`，多包了一層資料夾，
HA 完全掃不到**，導致使用者白等好幾輪。

keyfile 內容（`psk` 是明文，這是 NetworkManager 格式的限制）：

    [connection]
    id=<名稱>
    uuid=<固定的 UUID4，每次換會導致 IP 一直變>
    type=802-11-wireless

    [802-11-wireless]
    mode=infrastructure
    ssid=<SSID>
    powersave=2          # 關閉無線省電，否則連上後會莫名掉線且不重連

    [802-11-wireless-security]
    auth-alg=open
    key-mgmt=wpa-psk
    psk=<密碼>

    [ipv4]
    method=auto
    [ipv6]
    addr-gen-mode=stable-privacy
    method=auto

**設定寫進系統後隨身碟就能拔掉**（存在 `/mnt/overlay/etc/NetworkManager/system-connections/`），
重開機仍然有效。碟上的明文密碼記得清掉。

### ⚠ 那條網路線是壞的

原本要用有線，但接上樹莓派後完全沒有 DHCP。把同一條線插到 Mac 測試，
`en0` 顯示 `media: autoselect (none)`——**實體層收不到任何連線訊號**。

**樹莓派網路孔的燈會亮不代表線路真的通。** 這是誤導性最強的一個徵狀，
浪費了好幾輪排查。之後要用有線的話得換線或換孔。

### 下次繼續的起點

1. 換 5V/3A 電源，確認 HA 不再回報電壓不足
2. 插上 Zigbee 接收器（**黑色 USB 2.0 孔**，不要藍色 3.0，並用延長線拉開）
3. 確認 HA 的硬體清單認得到它（`/api/hassio/hardware/info` 看 tty 裝置）
4. 裝 Mosquitto → zigbee2mqtt → 配對 D1

## 之後要補的

- Zigbee 繼電器到貨後的接線與安全注意事項（涉及市電）
- iRobot 整合方式（HA 有官方整合，但要確認是雲端還是本地）
- 兩台 Pi 的備份策略

---

# 附錄：紅外線的操作步驟與限制

> 中樞相關的步驟（原步驟 0–3）已確認在 M3 上不可行，故移除。
> 以下是實際採用的博聯小黑豆那條路，仍然有效。

## 步驟 4：學紅外碼

> ⚠ **你在博聯 App 裡學過的碼我們拿不到。** 那些存在博聯雲端，
> 區網直連讀不到，所以要用樹莓派**重學一次**。
> 學完存成 `~/ir_codes.json`，之後永久有效且完全不碰雲端。

小黑豆要**插電並連上同一個 Wi-Fi**，然後：

```bash
ssh lpl1103@raspberrypi.local
python3 -c "import ir_remote; print(ir_remote.discover())"     # 先確認找得到小黑豆
python3 -c "import ir_remote; ir_remote.learn('風扇電源')"      # 然後拿實體遙控器對著它按
python3 -c "import ir_remote; print(ir_remote.known())"        # 看學會哪些
```

每個要用的按鍵學一次。名稱自己取，下一步的規則檔要用同樣的名稱。

## 步驟 5：寫對應規則

```bash
scp deploy/switch_rules.example.json lpl1103@raspberrypi.local:~/switch_rules.json
```

上去改成步驟 3、4 得到的實際值：

```json
{
  "158d0001abcdef": {
    "channel_0": { "click": "風扇電源" },
    "channel_1": { "click": "冷氣電源", "double_click": "冷氣強風" }
  }
}
```

**這個檔案每次事件都會重讀，改完不用重啟服務**，按一下開關就知道對不對。

## 步驟 6：啟動橋接服務

```bash
scp src/switch_bridge.py lpl1103@raspberrypi.local:~/
scp deploy/switch-bridge.service lpl1103@raspberrypi.local:/tmp/
ssh lpl1103@raspberrypi.local '
  sudo cp /tmp/switch-bridge.service /etc/systemd/system/ &&
  sudo systemctl daemon-reload &&
  sudo systemctl enable --now switch-bridge'
```

驗證：

```bash
ssh lpl1103@raspberrypi.local 'journalctl -u switch-bridge -f'
```

然後按開關，應該看到：

```
[bridge] 158d0001abcdef channel_0=click -> 發送紅外「風扇電源」: 已發送 風扇電源
```

---

## 疑難排解

| 症狀 | 檢查 |
|---|---|
| `aqara_discover.py` 找不到中樞 | 同網段？App 裡開了區網協定？中樞型號支援嗎？ |
| 找不到中樞但按按鈕**有事件進來** | 正常，有些韌體不回 `whois` 但照樣廣播。可以繼續 |
| 有事件但沒發紅外 | `sid`、欄位名稱、動作名稱有沒有跟規則檔對上？journal 會印「沒有對應規則」 |
| 按一次家電開了又關 | 去重沒生效或間隔太短。多數遙控器是 toggle，被觸發兩次就等於沒按。調 `switch_bridge.py` 的 `DEDUPE_SEC` |
| 找不到小黑豆 | 插電了嗎？同一個 Wi-Fi 嗎？博聯裝置只支援 2.4GHz |
| 紅外發了但家電沒反應 | 小黑豆要對得到家電的接收窗。碼學錯的話重學一次 |

## 已知限制

- **多播不跨網段**。中樞、樹莓派必須在同一個子網
- **中樞型號決定可行性**。新款拿掉區網協定的話這條路走不通
- **紅外是單向的**，發出去不知道家電有沒有收到，也讀不到家電目前狀態
- **多數遙控器的電源是 toggle**，同一個碼開也是它關也是它，
  所以「現在到底開著還關著」程式無從得知
