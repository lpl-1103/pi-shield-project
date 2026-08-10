#!/usr/bin/env python3
r"""
文件封存工具

功能：
- 掃描使用者個人資料夾（%USERPROFILE%，不含 AppData——那是應用程式自己的資料，
  不是使用者建立的文件）裡的常見文件類型檔案
- 找出「最後修改時間」超過指定天數（預設 365 天）沒動過的檔案
- 每個檔案各自獨立判斷、各自搬移，不是按副檔名分類集中堆放——例如 C:\1\2\3
  裡的檔案 4/5/6，只有 5、6 超過期限，4 會留在原地不動，5、6 各自搬到
  D:\Cmove\1\2\3\5、D:\Cmove\1\2\3\6，資料夾結構原封不動保留
- 搬到指定磁碟機（預設 D:）底下的一個前置目錄（預設 `Cmove`，可用 --dest-subdir
  改名），不會直接灌到目標磁碟根目錄跟原本就有的東西混在一起
- 搬移後在原路徑留一個 .lnk 捷徑指向新位置（捷徑檔案本身只有幾 KB，
  幾乎不佔空間，但能讓「最近使用的檔案」清單、其他捷徑還是找得到檔案）
- 跳過雲端同步的「僅供線上使用」佔位檔案（OneDrive 之類），避免誤搬或觸發下載
- 支援 dry-run（只列出候選清單，不實際搬移）
- 每次執行都會在腳本（或打包後 .exe）所在資料夾寫一份操作紀錄 JSON

為什麼用「最後修改時間」而不是「最後開啟時間」：Windows 從 Vista 開始，NTFS 預設
關閉了「最後存取時間」的自動更新（效能考量），這個時間戳在很多電腦上根本不準，
也可能被掃毒軟體/索引服務之類的背景程式意外更新。最後修改時間雖然語意上是
「最後被改過」而不是「最後開啟」，但至少是可靠、看得懂的指標。

注意：
- 不需要系統管理員權限（只動使用者自己的資料夾）
- 建議第一次先加 --dry-run 看看候選清單，確認沒問題再正式執行
- 搬移中的檔案如果正被其他程式開啟，會被跳過並記錄在 log 裡，不會強制搬移
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

if os.name != 'nt':
    print("此腳本僅支援 Windows（需要在 Windows 上運行）。")
    sys.exit(1)


DOCUMENT_EXTENSIONS = {
    '.doc', '.docx', '.pdf', '.xls', '.xlsx', '.ppt', '.pptx',
    '.txt', '.rtf', '.csv', '.odt', '.ods', '.odp',
}

EXCLUDED_DIR_NAMES = {'appdata', '$recycle.bin', 'system volume information'}

FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
FILE_ATTRIBUTE_REPARSE_POINT = 0x400


# ---------- 基礎工具 ----------

def get_user_profile() -> str:
    return os.environ.get('USERPROFILE') or str(Path.home())


def get_base_dir() -> str:
    """腳本或打包後 .exe 所在的資料夾，操作紀錄會寫在這裡，方便找到。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def human_size(n: float) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024.0:
            return f"{n:3.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}PB"


# ---------- 操作紀錄（方便事後查對） ----------

_LOG_PATH = None


def init_log() -> str:
    global _LOG_PATH
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    _LOG_PATH = os.path.join(get_base_dir(), f'move_documents_log_{ts}.json')
    with open(_LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump([], f)
    return _LOG_PATH


def log_action(action: str, src: str, dst: str, ok: bool, note: str = '') -> None:
    if not _LOG_PATH:
        return
    entry = {
        'time': datetime.datetime.now().isoformat(timespec='seconds'),
        'action': action,  # 'move' 或 'shortcut'
        'src': src,
        'dst': dst,
        'ok': ok,
        'note': note,
    }
    try:
        with open(_LOG_PATH, 'r', encoding='utf-8') as f:
            logs = json.load(f)
    except Exception:
        logs = []
    logs.append(entry)
    try:
        with open(_LOG_PATH, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---------- 掃描候選檔案 ----------

def should_skip_file(path: str) -> bool:
    """跳過 symlink、隱藏/系統檔案、以及雲端同步的佔位檔案（reparse point）——
    這些不是使用者一般認知裡的「文件」，搬了容易出問題（觸發雲端下載、弄壞同步狀態等）。"""
    try:
        if os.path.islink(path):
            return True
        attrs = os.stat(path).st_file_attributes
        return bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM | FILE_ATTRIBUTE_REPARSE_POINT))
    except (OSError, AttributeError):
        return True


def iter_candidate_files(root: str, cutoff_ts: float):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in EXCLUDED_DIR_NAMES]
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext not in DOCUMENT_EXTENSIONS:
                continue
            full = os.path.join(dirpath, name)
            if should_skip_file(full):
                continue
            try:
                st = os.stat(full)
            except (OSError, PermissionError):
                continue
            if st.st_mtime < cutoff_ts:
                yield full, st.st_size, st.st_mtime


# ---------- 捷徑 / 搬移 ----------

def create_shortcut(link_path: str, target_path: str) -> bool:
    # 用 PowerShell 的 WScript.Shell COM 物件建立 .lnk，不用額外裝 pywin32
    ps_script = (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{link_path}'); "
        f"$s.TargetPath = '{target_path}'; $s.Save()"
    )
    res = subprocess.run(['powershell', '-NoProfile', '-Command', ps_script],
                          capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  建立捷徑失敗：{(res.stderr or res.stdout).strip()}")
        return False
    return True


def move_one_file(src: str, dst: str) -> bool:
    if os.path.exists(dst):
        print(f"  略過：目的地已存在 {dst}")
        log_action('move', src, dst, False, note='destination exists')
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        shutil.move(src, dst)
    except (OSError, PermissionError, shutil.Error) as e:
        print(f"  搬移失敗（可能檔案正被使用中）：{e}")
        log_action('move', src, dst, False, note=str(e))
        return False
    log_action('move', src, dst, True)

    link_path = src + '.lnk'
    ok = create_shortcut(link_path, dst)
    log_action('shortcut', link_path, dst, ok)
    return True


# ---------- 主流程 ----------

def main():
    p = argparse.ArgumentParser(description='把 C 槽超過指定天數沒修改的文件搬到 D 槽同樣的相對路徑下')
    p.add_argument('--dest-drive', default='D:', help='目標磁碟機代號，預設 D:')
    p.add_argument('--dest-subdir', default='Cmove',
                    help='目標磁碟底下的前置目錄名稱，避免直接灌到 D 槽根目錄跟現有東西混在一起，預設 Cmove')
    p.add_argument('--days', type=int, default=365, help='幾天沒修改才算候選，預設 365')
    p.add_argument('--dry-run', action='store_true', help='只列出候選清單，不實際搬移，建議第一次先用這個看看')
    p.add_argument('--yes', action='store_true', help='跳過確認直接搬移全部候選（請先用 --dry-run 確認過行為）')
    args = p.parse_args()

    print("=" * 60)
    print("文件封存工具：C 槽超過期限沒修改的文件 -> D 槽")
    print("=" * 60)

    user_profile = get_user_profile()
    dest_drive = args.dest_drive.rstrip('\\/')
    if not os.path.exists(dest_drive + '\\'):
        print(f"找不到目標磁碟 {dest_drive}，請確認磁碟機代號正確。")
        sys.exit(2)
    dest_root = os.path.join(dest_drive + '\\', args.dest_subdir)

    cutoff_ts = time.time() - args.days * 86400
    print(f"掃描範圍：{user_profile}（不含 AppData）")
    print(f"條件：副檔名屬於文件類型，且最後修改時間超過 {args.days} 天")
    print(f"目的地：{dest_root}\\（保留原本的資料夾結構，只是前面多一層 {args.dest_subdir}）\n")
    print("掃描中（第一次可能要等一下）...")

    candidates = list(iter_candidate_files(user_profile, cutoff_ts))
    if not candidates:
        print('沒有找到符合條件的檔案。')
        return

    total_size = sum(size for _, size, _ in candidates)
    print(f"\n找到 {len(candidates)} 個候選檔案，總共 {human_size(total_size)}：\n")
    for path, size, mtime in candidates[:50]:
        mtime_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
        print(f"  {path} — {human_size(size)} — 最後修改 {mtime_str}")
    if len(candidates) > 50:
        print(f"  ...還有 {len(candidates) - 50} 個，完整清單之後可以在操作紀錄裡看")

    free = shutil.disk_usage(dest_drive + '\\').free
    if free < total_size * 1.05:
        print(f"\n⚠️ 目標磁碟 {dest_drive} 可用空間不足（剩 {human_size(free)}，需要約 {human_size(total_size)}），中止。")
        sys.exit(2)

    if args.dry_run:
        print("\nDRY RUN 模式，以上是模擬結果，沒有實際搬移任何檔案。")
        return

    if not args.yes:
        ans = input(f"\n確定要搬移以上 {len(candidates)} 個檔案到 {dest_root} 嗎？(y/N)：").strip().lower()
        if ans != 'y':
            print('已取消。')
            return

    log_path = init_log()
    print(f"\n操作紀錄會寫在：{log_path}\n")

    moved, skipped, freed = 0, 0, 0
    for src, size, mtime in candidates:
        drive_root = os.path.splitdrive(src)[0] + '\\'
        rel = os.path.relpath(src, drive_root)
        dst = os.path.join(dest_root, rel)
        if move_one_file(src, dst):
            moved += 1
            freed += size
        else:
            skipped += 1

    print("\n" + "=" * 60)
    print(f"完成：搬移 {moved} 個檔案，釋放 {human_size(freed)}，略過/失敗 {skipped} 個。")
    print(f"完整操作紀錄：{log_path}")


if __name__ == '__main__':
    main()
