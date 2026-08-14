# 無線開關 → 紅外線：設定步驟

> **目標**：按一下 Aqara D1 雙鍵無線開關 → 中樞收到 → 樹莓派收到 → 小黑豆發紅外 → 家電動作。
>
> **狀態（2026-08-13）**：程式已寫好並用假事件驗證過分派邏輯，
> **但還沒對真實硬體跑過**——中樞當時還沒插電。以下是拿到電源後照著做的步驟。

## 為什麼中間要有樹莓派

Aqara 跟博聯是**兩個互不相通的生態系**：

| | Aqara 中樞 | 博聯小黑豆 |
|---|---|---|
| 通訊 | Zigbee（對子裝置）+ 自家雲端 | Wi-Fi + 自家雲端 |
| 開放介面 | 區域網路通訊協定（部分型號） | 區網直連（`python-broadlink`） |

**Aqara App 裡沒有「控制博聯裝置」這個選項**，兩邊的雲端也不互通。
D1 → 中樞這段是原生 Zigbee 沒問題，但中樞 → 小黑豆這段需要有人翻譯，
樹莓派就是翻譯的那個人。

```
D1 開關 ──Zigbee──> Aqara 中樞 ──UDP 多播──> 樹莓派 ──區網──> 小黑豆 ──紅外──> 家電
                              switch_bridge.py + aqara_hub.py + ir_remote.py
```

全程**不經過任何雲端**，中樞跟小黑豆的伺服器掛掉都不影響。

---

## 步驟 0：先確認中樞支不支援（這一步決定整條路走不走得通）

這個做法依賴中樞的「**區域網路通訊協定**」（有些韌體叫「開發者模式」）。

- **舊款有**：小米閘道器 v2、Aqara M1S、M2
- **新款有些拿掉了**：如果 App 裡找不到這個開關，這條路就走不通

找不到的話有兩條替代路線，到時候再談：

- **Zigbee 接收器**：買一支 USB Zigbee dongle 插樹莓派，D1 直接跟樹莓派配對，
  完全不需要中樞。鏈路最短最穩，代價是多一個硬體
- **Home Assistant**：樹莓派多跑一套服務，兩邊整合都現成，但比較重

---

## 步驟 1：中樞插電並配對 D1 開關

1. 中樞接電源，用 Aqara App 加入，**連到跟樹莓派同一個 Wi-Fi**
   （樹莓派目前在 `192.168.0.x`。**多播不跨網段**，2.4G/5G 若被路由器隔離也會失敗）
2. App 裡把 D1 雙鍵開關配對到中樞
3. 先在 App 裡按按鈕，確認中樞收得到（App 應該會有反應）——
   這一步不通的話後面都別試

## 步驟 2：開啟區域網路通訊協定

Aqara App → 選中樞 → 設定 → **區域網路通訊協定**（開啟）

> 只需要「讀」事件的話**不需要金鑰**，中樞是明文廣播。
> 要「控制」中樞上的裝置才需要那把 AES 金鑰——我們用不到，
> 少一個會過期的依賴。

## 步驟 3：確認樹莓派收得到

```bash
scp deploy/aqara_discover.py src/aqara_hub.py lpl1103@raspberrypi.local:~/
ssh lpl1103@raspberrypi.local 'python3 ~/aqara_discover.py'
```

跑起來後**按幾下 D1 開關**——左鍵、右鍵、雙擊、長按各試一次。畫面會印出：

```
時間     cmd       model                      sid                data
14:23:01 report    remote.b286acn01           158d0001abcdef     {"channel_0": "click"}
```

**把 `model`、`sid`、還有 `data` 裡的欄位名稱記下來**，下一步要用。

> ⚠ 欄位名稱（`channel_0` / `button_0` / `dual_channel`）**會因為批次與韌體而不同**，
> 所以程式刻意不預設它叫什麼，一律以這裡印出來的為準。

**印不出東西的話**依序檢查：同網段？App 裡開了區網協定？中樞型號支援嗎？

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
