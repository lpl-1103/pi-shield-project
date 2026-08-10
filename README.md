# Hardware Development

硬體相關案子的總目錄。**一個資料夾一個案子**，每個案子內部再依功能分（`src/` 程式、`docs/` 文件、資料另外放）。

> 2026-08-07 重整。在此之前所有案子的檔案都平鋪在這一層，`karaoke.py` 跟
> `move_windows_apps.py` 躺在一起、四份 README/HANDOFF 互相看不出屬於誰。

## 案子

| 案子 | 內容 | 狀態 |
|---|---|---|
| [`projects/am62a-inspection-station/`](projects/am62a-inspection-station/) | **AM62A 智慧驗貨站**——電子零件進貨標籤辨識入庫。TI AM62A 開發板 + C7x/MMA NPU，手機當鏡頭 | 進行中，辨識器已跑在板子的 NPU 上 |
| [`projects/pi3-karaoke/`](projects/pi3-karaoke/) | **樹莓派點歌機 + LINE Bot**——LINE 點歌、mpv 播放、歌詞同步、大螢幕歌詞牆 | 可用，systemd 開機自動啟動 |
| [`projects/frdm-mcxa153/`](projects/frdm-mcxa153/) | **NXP FRDM-MCXA153**——Zephyr llext 動態載入實驗 | 實驗階段 |
| [`projects/windows-app-migration/`](projects/windows-app-migration/) | **Windows 應用搬移工具**——把已安裝的程式與舊文件搬到別的磁碟，含打包好的 .exe | 工具，可直接用 |

## 資料

| 路徑 | 內容 | 誰在用 |
|---|---|---|
| [`data/erp-history/`](data/erp-history/) | 進貨明細（2015-09 ~ 2026-07）與歷史進貨單，xlsx / numbers | 驗貨站的 ERP 比對來源 |

> ⚠ 驗貨站的程式讀的是它 **repo 內部**那份副本
> （`projects/am62a-inspection-station/golden_samples/黃金資料/進貨單/歷史進貨單數據.xlsx`），
> 不是 `data/erp-history/`。這裡放的是原始資料，改了不會影響程式。

## 版本控制

這一層的 git repo 追蹤的是 **pi3-karaoke** 案子（重整前它的檔案就直接放在根目錄）。
`projects/am62a-inspection-station/` 有**自己獨立的 git repo**，兩者不互相干擾。
`frdm-mcxa153`、`windows-app-migration`、`data/` 目前沒納入版控。
