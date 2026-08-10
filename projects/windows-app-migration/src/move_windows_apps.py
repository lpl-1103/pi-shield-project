#!/usr/bin/env python3
"""
Windows 應用搬移工具

功能：
- 自動搜尋常見安裝資料夾中的大型應用資料夾
- 將選定的應用移動到指定的 D:\\應用程序\\<AppName> 下
- 對原始位置建立 NTFS Junction (/J)，以保留原路徑不變（其他程式/捷徑找得到）
- 可選擇一併搬移該應用在 AppData/ProgramData 裡的關聯資料（嚴格比對，搬前會列出來讓你確認）
- 支援 dry-run（只模擬不動手）、互動確認、單一應用失敗自動回滾
- 每次執行都會在腳本（或打包後 .exe）所在資料夾寫一份操作紀錄 JSON，方便事後查對/手動復原

注意：
- 請以系統管理員權限執行（右鍵 > 以系統管理員身分執行）。
- 建議第一次先加 --dry-run 看看它會做什麼，確認沒問題再正式執行。
- 搬移前請先關閉要搬移的應用程式，避免檔案被鎖定導致搬到一半失敗。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

if os.name != 'nt':
    print("此腳本僅支援 Windows（需要在 Windows 上運行）。")
    sys.exit(1)


# ---------- 基礎工具 ----------

def is_admin() -> bool:
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


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


def normalize_name(s: str) -> str:
    """只留英數字，拿來做「去掉雜訊字元後比對」，例如 'My-App' 跟 'My App' 視為相同。"""
    return ''.join(ch for ch in s.lower() if ch.isalnum())


# ---------- 操作紀錄（方便事後查對/手動復原） ----------

_LOG_PATH = None


def init_log() -> str:
    global _LOG_PATH
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    _LOG_PATH = os.path.join(get_base_dir(), f'move_apps_log_{ts}.json')
    with open(_LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump([], f)
    return _LOG_PATH


def log_action(action: str, src: str, dst: str, ok: bool, note: str = '') -> None:
    if not _LOG_PATH:
        return
    entry = {
        'time': datetime.datetime.now().isoformat(timespec='seconds'),
        'action': action,  # 'move' 或 'junction'
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


# ---------- 受保護資料夾：這些不該被搬走，會弄壞其他軟體或系統本身 ----------

PROTECTED_NAMES = {
    'common files', 'common files (x86)', 'windowsapps', 'internet explorer',
    'windows defender', 'windows defender advanced threat protection',
    'windows mail', 'windows media player', 'windows nt', 'windows photo viewer',
    'windows portable devices', 'windows security', 'windowspowershell',
    'microsoft', 'microsoft.net', 'reference assemblies', 'msbuild',
    'installshield installation information', 'package cache',
}

COMMON_ROOTS = [
    r"C:\Program Files",
    r"C:\Program Files (x86)",
]


# ---------- 掃描候選應用 ----------

def get_folder_size(path: str) -> int:
    """算資料夾大小；用 scandir 一次拿到 stat 資訊比較快，且跳過 junction/symlink 避免重複計算或繞圈。"""
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        total += get_folder_size(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError):
        pass
    return total


def find_candidates(min_size_bytes: int, show_progress: bool = True):
    candidates = []
    roots = COMMON_ROOTS + [os.path.join(get_user_profile(), 'AppData', 'Local', 'Programs')]
    for root in roots:
        if not os.path.exists(root):
            continue
        try:
            names = os.listdir(root)
        except Exception:
            continue
        for name in names:
            if name.lower() in PROTECTED_NAMES:
                continue
            full = os.path.join(root, name)
            if not os.path.isdir(full):
                continue
            if os.path.islink(full):
                continue
            if show_progress:
                print(f"  掃描中: {name}...".ljust(70), end='\r')
            size = get_folder_size(full)
            if size >= min_size_bytes:
                candidates.append((full, name, size))
    if show_progress:
        print(' ' * 70, end='\r')

    seen = set()
    uniq = []
    for p, n, s in sorted(candidates, key=lambda x: -x[2]):
        if p not in seen:
            uniq.append((p, n, s))
            seen.add(p)
    return uniq


# ---------- 執行中程序偵測 ----------

def get_running_exe_paths():
    """回傳目前所有執行中程序的執行檔路徑（小寫）；查不到時回傳 None 表示「無法判斷」。"""
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             'Get-Process | Where-Object {$_.Path} | Select-Object -ExpandProperty Path'],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return None
        return {line.strip().lower() for line in result.stdout.splitlines() if line.strip()}
    except Exception:
        return None


def is_app_running(src_path: str, running_paths) -> bool:
    if not running_paths:
        return False
    src_lower = os.path.normpath(src_path).lower()
    return any(p.startswith(src_lower) for p in running_paths)


# ---------- 搬移 / Junction ----------

def create_junction(src: str, dst: str, dry_run: bool = False) -> int:
    if dry_run:
        print(f"DRY RUN: mklink /J \"{src}\" \"{dst}\"")
        return 0
    print(f"建立 Junction: {src} -> {dst}")
    # 用參數陣列而不是 shell=True 拼字串，避免路徑裡的特殊字元被當成 shell 語法解讀
    res = subprocess.run(['cmd', '/c', 'mklink', '/J', src, dst], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  mklink 失敗：{(res.stderr or res.stdout).strip()}")
    return res.returncode


def check_disk_space(dest_root: str, required_bytes: int):
    """回傳目的地磁碟的可用空間；查不到回傳 None（不阻擋，但也沒辦法事先警告）。"""
    try:
        drive = os.path.splitdrive(os.path.abspath(dest_root))[0] + os.sep
        return shutil.disk_usage(drive).free
    except Exception:
        return None


def safe_move(src: str, dst: str, dry_run: bool = False) -> bool:
    if os.path.exists(dst):
        print(f"  略過：目的地已存在 {dst}（可能已經搬過了，不要重複搬移覆蓋掉既有資料）")
        return False
    dst_parent = os.path.dirname(dst)
    if not dry_run:
        os.makedirs(dst_parent, exist_ok=True)
    print(f"搬移: {src} -> {dst}")
    if dry_run:
        return True
    try:
        shutil.move(src, dst)
        return True
    except Exception as e:
        print(f"  搬移失敗：{e}")
        return False


# ---------- 關聯資料（嚴格比對，需要使用者確認才會搬） ----------

def find_related_paths(app_name: str):
    """嚴格比對：資料夾名稱要跟 app_name 完全相同、或去除空格/符號後相同才算，
    不再用寬鬆的 substring 互相包含（避免像 'Go' 誤配到 'GoogleDrive' 這種狀況）。
    刻意不搜尋 Downloads——那是使用者下載的檔案，跟「應用程式資料」是兩回事。
    """
    up = get_user_profile()
    search_paths = [
        os.path.join(up, 'AppData', 'Local'),
        os.path.join(up, 'AppData', 'Roaming'),
        r"C:\ProgramData",
    ]
    target = normalize_name(app_name)
    candidates = []
    for base in search_paths:
        if not os.path.exists(base):
            continue
        try:
            names = os.listdir(base)
        except Exception:
            continue
        for name in names:
            if normalize_name(name) == target:
                full = os.path.join(base, name)
                if os.path.isdir(full) and not os.path.islink(full):
                    candidates.append(full)
    return candidates


def move_one(src: str, dst: str, dry_run: bool) -> bool:
    """搬移 + 建 junction，失敗時盡量回滾，回傳是否成功。"""
    ok = safe_move(src, dst, dry_run=dry_run)
    log_action('move', src, dst, ok)
    if not ok:
        return False

    rc = create_junction(src, dst, dry_run=dry_run)
    log_action('junction', src, dst, rc == 0)
    if rc != 0:
        print("  建立 Junction 失敗，回滾搬移...")
        if not dry_run:
            try:
                shutil.move(dst, src)
                log_action('rollback-move', dst, src, True)
            except Exception as e:
                print(f"  回滾也失敗了：{e}")
                print(f"  資料目前卡在：{dst}，請手動處理（可以參考操作紀錄檔）。")
                log_action('rollback-move', dst, src, False, note=str(e))
        return False
    return True


def move_app_and_related(src_path: str, app_name: str, dest_root: str, related_to_move,
                          dry_run: bool = False):
    dst_app = os.path.join(dest_root, app_name)

    if not move_one(src_path, dst_app, dry_run):
        return False

    for r in related_to_move:
        rel_name = os.path.basename(r)
        new_loc = os.path.join(dest_root, app_name, 'related', rel_name)
        move_one(r, new_loc, dry_run)  # 個別失敗不影響主程式已經搬移成功的結果，只印警告

    return True


# ---------- 主流程 ----------

def prompt_yes_no(question: str, default_no: bool = True) -> bool:
    suffix = '(y/N)' if default_no else '(Y/n)'
    ans = input(f"{question} {suffix}：").strip().lower()
    if not ans:
        return not default_no
    return ans == 'y'


def main():
    p = argparse.ArgumentParser(description='把大型 Windows 應用搬到指定磁碟，並在原位置建立 Junction 保留路徑')
    p.add_argument('--dest-root', default=r"D:\應用程序", help='目標根目錄，預設 D:\\應用程序')
    p.add_argument('--min-size-mb', type=int, default=200, help='最小資料夾大小 (MB) 才會列為候選，預設 200')
    p.add_argument('--dry-run', action='store_true', help='只模擬不執行，建議第一次先用這個看看')
    p.add_argument('--auto', action='store_true', help='不用一個個選，全部候選都處理（會另外要求一次總確認）')
    p.add_argument('--yes', action='store_true', help='跳過所有互動確認（自動化/腳本化執行用，請先用 --dry-run 確認過行為）')
    args = p.parse_args()

    print("=" * 60)
    print("Windows 應用搬移工具")
    print("=" * 60)
    print("會做的事：把選定的應用資料夾搬到指定磁碟，並在原位置留一個")
    print("Junction 指回去，讓其他程式/捷徑還是找得到它。")
    print("不確定的話，建議先加 --dry-run 跑一次看看會動到哪些東西。\n")

    if not is_admin():
        print('請以系統管理員權限執行此腳本（右鍵 > 以系統管理員身分執行）。')
        sys.exit(2)

    log_path = init_log()
    print(f"本次操作紀錄會寫在：{log_path}\n")

    dest_root = args.dest_root
    min_size = args.min_size_mb * 1024 * 1024

    print(f"搜尋大小 >= {args.min_size_mb}MB 的應用候選中（第一次掃描可能要等一下）...")
    candidates = find_candidates(min_size_bytes=min_size)

    if not candidates:
        print('未找到符合條件的資料夾。可以降低 --min-size-mb 再試試。')
        return

    print('\n候選應用：')
    for i, (pth, name, size) in enumerate(candidates, 1):
        print(f"{i}. {name} — {pth} — {human_size(size)}")

    if args.auto:
        print(f"\n--auto 模式：將處理以上全部 {len(candidates)} 個候選。")
        if not args.yes and not prompt_yes_no('確定要繼續嗎？', default_no=True):
            print('已取消。')
            return
        to_process = candidates
    else:
        sel = input('\n輸入要搬移的編號，使用逗號分隔（例如 1,3）或輸入 all：').strip()
        if sel.lower() == 'all':
            choices = [str(i) for i in range(1, len(candidates) + 1)]
        else:
            choices = [s.strip() for s in sel.split(',') if s.strip().isdigit()]
        to_process = [candidates[int(c) - 1] for c in choices if 0 <= int(c) - 1 < len(candidates)]

    if not to_process:
        print('沒有選擇任何應用，結束。')
        return

    running_paths = get_running_exe_paths()
    if running_paths is None:
        print('\n（無法偵測目前執行中的程序，請自行確認要搬移的應用都已經關閉。）')

    print('\n開始處理...')
    results = []
    for src, name, size in to_process:
        print(f'\n--- {name} ({human_size(size)}) ---')

        if is_app_running(src, running_paths):
            print(f'⚠️  偵測到 {name} 目前可能正在執行中，繼續搬移有機會因為檔案被鎖定而失敗或損毀安裝。')
            if not args.yes and not prompt_yes_no('請先關閉該程式。仍要繼續嗎？', default_no=True):
                print(f'已略過 {name}。')
                results.append((name, 'skipped'))
                continue

        free = check_disk_space(dest_root, size)
        if free is not None and free < size * 1.05:
            print(f'⚠️  目的地磁碟可用空間不足（剩 {human_size(free)}，需要約 {human_size(size)}），略過 {name}。')
            results.append((name, 'insufficient-space'))
            continue

        related_to_move = []
        related = find_related_paths(name)
        if related:
            print(f'找到 {name} 可能的關聯資料（AppData/ProgramData）：')
            for r in related:
                print(f'  - {r}')
            if args.yes:
                related_to_move = related if args.auto else []
            elif prompt_yes_no('要一併搬移這些關聯資料嗎？', default_no=True):
                related_to_move = related

        ok = move_app_and_related(src, name, dest_root, related_to_move, dry_run=args.dry_run)
        results.append((name, 'ok' if ok else 'failed'))
        if ok:
            print(f'✅ 完成：{name} 已搬移到 {dest_root} 並建立 Junction。')
        else:
            print(f'❌ 失敗：{name} 未成功完成，已嘗試回滾（詳見操作紀錄 {log_path}）。')

    print('\n' + '=' * 60)
    print('處理結果總覽：')
    for name, status in results:
        print(f'  {name}: {status}')
    print(f'\n完整操作紀錄：{log_path}')
    print('請檢查搬移過的應用是否能正常啟動。')


if __name__ == '__main__':
    main()
