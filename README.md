# Hardware Development

硬體相關案子的總目錄。**一個資料夾一個案子**，每個案子內部依固定慣例分層。

> 2026-08-07 第一次重整（在此之前所有檔案平鋪在根目錄，`karaoke.py` 跟
> `move_windows_apps.py` 躺在一起）。
> 2026-08-12 第二次整理：補上部署產物與 Mac 端相依、統一文件慣例、清掉冗餘檔。

## 案子

| 案子 | 內容 | 狀態 |
|---|---|---|
| [`projects/am62a-inspection-station/`](projects/am62a-inspection-station/) | **AM62A 智慧驗貨站**——電子零件進貨標籤辨識入庫。TI AM62A 開發板 + C7x/MMA NPU，手機當鏡頭 | 進行中，辨識器已跑在板子的 NPU 上 |
| [`projects/pi3-karaoke/`](projects/pi3-karaoke/) | **小樂點歌台**——LINE 點歌機器人 + 樹莓派播放系統。自然語言理解、語音點歌、麥克風語音控制、歌詞同步、大螢幕歌詞牆 | 運作中，三個 systemd 服務開機自動啟動 |
| [`projects/frdm-mcxa153/`](projects/frdm-mcxa153/) | **NXP FRDM-MCXA153**——Zephyr llext 動態載入實驗 | 實驗階段 |
| [`projects/windows-app-migration/`](projects/windows-app-migration/) | **Windows 搬移工具**——把已安裝程式與久未開啟的文件搬到別的磁碟，含打包好的 .exe | 工具，可直接用 |

## 資料

| 路徑 | 內容 | 誰在用 |
|---|---|---|
| [`data/erp-history/`](data/erp-history/) | 進貨明細（2015-09 ~ 2026-07）與歷史進貨單，xlsx / numbers | 驗貨站的 ERP 比對來源 |

> ⚠ 驗貨站的程式讀的是它 **repo 內部**那份副本
> （`projects/am62a-inspection-station/golden_samples/黃金資料/進貨單/歷史進貨單數據.xlsx`），
> 不是 `data/erp-history/`。這裡放的是原始資料，改了不會影響程式。

## 目錄慣例

每個案子一律照這個結構擺，找東西不用猜：

```
projects/<案子>/
├── README.md          這個案子是什麼、怎麼跑起來
├── src/               程式本體
├── docs/
│   ├── HANDOFF.md     交接文件：架構、部署、維運、疑難排解、開發歷程
│   ├── reports/       週報，檔名一律 <起日>_<迄日>.md（例如 2026-07-16_2026-07-21.md）
│   └── *.md           其他文件（操作手冊等）
├── deploy/            systemd unit、設定檔範本、部署腳本（部署到機器上的東西）
└── requirements.txt   依賴，如果有的話
```

規則：

- **文件一律 Markdown**，不要 HTML、不要 .docx、不要 .zip 包原始碼
- **週報放 `docs/reports/`**，檔名用日期區間，不要 `WEEKLY_REPORT.md` 這種會互相蓋掉的名字
- **一個案子一份 `HANDOFF.md`**，新內容往下追加，不要另開新檔造成資訊分散
- **部署到機器上的東西要進 `deploy/`**。只存在於機器上的設定檔，機器一掛就得憑記憶重建
- **密鑰不進 git**，放範本（`*.example.json`）並在 `.gitignore` 擋掉真的那份

## 版本控制

這一層的 git repo（`pi-shield-project`）追蹤 `projects/` 底下除了驗貨站以外的所有案子，
以及 `data/`。

`projects/am62a-inspection-station/` 有**自己獨立的 git repo**，所以在 `.gitignore` 裡排除
——不排除的話外層會把它當成 gitlink，clone 下來只會拿到一個空目錄。

**這個 repo 是公開的。** 開發紀錄裡的實際密碼與密鑰（SSH/sudo 密碼、LINE Channel
Secret/Token、ngrok authtoken、ngrok 網域）都已改成佔位文字，只保留架構與邏輯本身。

## 打包搬移

```bash
scripts/pack.sh code     # 程式碼+文件+DB，約 40MB
scripts/pack.sh full     # 加上模型權重與 NPU artifacts，約 200MB
scripts/pack.sh all      # 全部含黃金照片，9.6GB
```
