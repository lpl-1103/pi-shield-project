# 把 move_windows_apps.py / move_old_documents.py 打包成 .exe

這一步需要在 **Windows 機器**上執行（PyInstaller 沒辦法從 Mac 跨平台編譯出 Windows 執行檔，我這邊沒辦法幫你完成這步，只能把指令準備好）。如果連 Windows 機器都沒有，可以考慮用 GitHub Actions 的 Windows 雲端執行環境跑打包（需要另外設定 workflow，之前有跟你聊過這個選項）。

這個資料夾裡有兩個獨立的小工具，打包方式幾乎一樣，差別只在要不要加 `--uac-admin`：

- **`move_windows_apps.py`**：搬大型應用程式資料夾，會動到 `Program Files` 之類需要系統管理員權限的地方，打包時要加 `--uac-admin`。
- **`move_old_documents.py`**：搬使用者自己文件夾裡放很久沒動的文件，只動 `%USERPROFILE%` 底下的東西，**不需要系統管理員權限**，打包時不要加 `--uac-admin`。

## 步驟

1. 確認 Windows 上有裝 Python 3（[python.org](https://www.python.org/) 下載安裝時記得勾選 "Add python.exe to PATH"）。

2. 開命令提示字元（不用系統管理員權限也可以，這步只是打包），切到腳本所在的資料夾，安裝 PyInstaller：

   ```bat
   pip install pyinstaller
   ```

3. 執行打包指令：

   ```bat
   pyinstaller --onefile --name MoveWindowsApps --uac-admin move_windows_apps.py
   pyinstaller --onefile --name MoveOldDocuments move_old_documents.py
   ```

   參數說明：
   - `--onefile`：打包成單一 .exe 檔，方便直接分享/搬到別台電腦用。
   - `--name`：輸出檔名，可以自己改。
   - `--uac-admin`（只有 `move_windows_apps.py` 需要）：會在 .exe 裡嵌入一個 manifest，讓使用者「直接點兩下」執行時，Windows 會自動跳出 UAC 提示要求系統管理員權限，不用自己手動右鍵「以系統管理員身分執行」。`move_old_documents.py` 因為只動使用者自己的資料夾，不需要這個權限，加了反而是不必要的提權。
   - 沒有加 `--windowed` / `--noconsole`：兩個工具都故意保留主控台視窗，因為都需要在終端機裡跟使用者互動（選項確認、dry-run 結果），如果隱藏主控台視窗，這些輸入提示會看不到。

4. 打包完成後，執行檔會在 `dist\MoveWindowsApps.exe` / `dist\MoveOldDocuments.exe`。這些檔案可以直接複製到任何 Windows 電腦上單獨執行，不需要另外裝 Python。

## 建議測試流程

1. 先用命令提示字元跑 `--dry-run`，確認掃到的候選、以及會不會誤判到不該搬的東西，看起來沒問題再拿掉 `--dry-run` 正式執行。
   - `MoveWindowsApps.exe --dry-run`
   - `MoveOldDocuments.exe --dry-run`
2. `MoveWindowsApps.exe` 正式執行前，先手動關閉你要搬移的那些應用程式。
3. 每次執行都會在 .exe 所在的資料夾產生一份操作紀錄 JSON（`move_apps_log_<時間戳記>.json` / `move_documents_log_<時間戳記>.json`），記錄了每一步搬移/建立 Junction/建立捷徑的結果，如果之後發現哪裡不對，可以照這份紀錄手動排查或復原。
4. `MoveOldDocuments.exe` 預設掃「一年以上沒修改」的文件，覺得太嚴格或太寬鬆可以用 `--days` 調整，例如 `--days 180` 改成半年。
5. `MoveOldDocuments.exe` 預設會搬到 `D:\Cmove\` 底下（保留原本相對路徑，例如 `C:\1\2\3\5.docx` 會搬到 `D:\Cmove\1\2\3\5.docx`），不會直接灌到 D 槽根目錄跟原本的東西混在一起。想改目錄名稱可以用 `--dest-subdir`，例如 `--dest-subdir 舊文件`。

## 之後要更新程式碼

改完 `.py` 檔之後，重新在 Windows 上跑一次上面對應的 `pyinstaller` 指令，`dist` 資料夾裡的 .exe 就會被覆蓋成最新版本。
