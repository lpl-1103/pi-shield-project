#!/usr/bin/env python3
"""熱門電台的動態歌曲池——讓連續播放好幾小時都不重複。

## 問題

原本的做法是 `POPULAR_SONGS` 這個寫死的清單，**每個分類只有 12 首**。
12 首約 48 分鐘就播完一輪，之後只能重複。程式註解自己也承認這點：

> 「如果整個分類（目前每類只有 12 首）都在 12 小時內播過了，才會退回允許重複
>   ——這是清單本來就小、遲早會繞回來的必然結果，不是 bug」

但使用者的實際需求是**連續播 4 小時（約 60 首）不重複**，差了 5 倍。

## 做法

不再寫死歌單，改成用多組「種子關鍵字」去 YouTube 搜尋，累積成幾百首的候選池。
種子是歌手/主題（例如「周杰倫」「五月天」「華語情歌」），每個種子抓 20~30 首，
十幾個種子就有數百首，足夠播一整天。

池子**背景預先擴充**：播放中就一邊抓下一批，不會讓使用者等。

## 「一次播放期間不重複」怎麼定義

使用者的要求很明確：

> 「我點了流行歌播放，一直放可能 4 小時，這四小時之間都不要重複歌曲，
>   我說暫停後下一次開始如果有少部分跟前面那四小時重複那沒關係」

所以用**兩層排除**：

  1. `session_played` —— 這次電台開著期間播過的，**`stop_radio()` 時才清空**。
     這是硬性的，池子沒歌了寧可去抓更多，也不重複。
  2. 12 小時歷史 —— 原本就有的，跨 session 的軟性排除，池子夠大時順便避開。

第 1 層是新的，也是解決使用者問題的關鍵。
"""
import random
import subprocess
import threading
import time

# 每個分類的種子關鍵字。**種子要夠散**——都用同一個歌手會抓到大量重複。
# 混合「歌手」「曲風」「年代」三種類型，池子的多樣性才夠。
SEEDS = {
    'cpop': [
        '周杰倫', '五月天', '林俊傑', '陳奕迅', '鄧紫棋', '蔡依林',
        '張惠妹', '孫燕姿', '田馥甄', '告五人', '茄子蛋', '八三夭',
        '華語 情歌 經典', '華語 KTV 必點', '90年代 國語金曲',
        '2000年代 華語 流行', '華語 抒情歌', '台語 經典',
    ],
    'kpop': [
        'BTS', 'BLACKPINK', 'NewJeans', 'IVE', 'LE SSERAFIM', 'TWICE',
        'Stray Kids', 'SEVENTEEN', 'aespa', 'ITZY', 'Red Velvet', 'EXO',
        'kpop hits playlist', 'kpop 2020s hits', 'kpop ballad',
    ],
    'epop': [
        'Ed Sheeran', 'Taylor Swift', 'The Weeknd', 'Dua Lipa', 'Bruno Mars',
        'Justin Bieber', 'Ariana Grande', 'Adele', 'Maroon 5', 'Coldplay',
        'Billie Eilish', 'Olivia Rodrigo',
        'pop hits 2020s', '80s pop classics', 'english ballad classics',
    ],
}

PER_SEED = 25          # 每個種子抓幾首
MIN_POOL = 80          # 池子低於這個數量就在背景補
FETCH_TIMEOUT = 30

_lock = threading.RLock()
_pool = {}             # category -> [{'title','id','query'}]
_seed_cursor = {}      # category -> 下一個要抓的種子索引
_session_played = set()   # 這次電台開著期間播過的 video_id 與標題 key
_filling = set()       # 正在背景抓的分類，避免重複觸發


def _fetch_seed(keyword, count=PER_SEED):
    """抓一個種子的歌。回傳 [{'title','id'}]，失敗回空清單。"""
    target = f'ytsearch{count}:{keyword}'
    try:
        r = subprocess.run(
            ['yt-dlp', '--flat-playlist', '--print', '%(title)s', '--print', '%(id)s',
             '--print', '%(duration)s', target],
            capture_output=True, text=True, timeout=FETCH_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError):
        return []
    lines = r.stdout.strip().splitlines()
    out = []
    for i in range(0, len(lines) - 2, 3):
        title, vid, dur = lines[i], lines[i + 1], lines[i + 2]
        # ⚠ 搜尋結果裡會混進**頻道**（不是影片），它的 duration 是 `NA`。
        # 第一版寫「拿不到長度就放行」，結果池子裡第一筆是「周杰倫 Jay Chou」
        # 這個頻道本身，播下去只會失敗。**拿不到長度就直接跳過。**
        try:
            d = float(dur)
        except (TypeError, ValueError):
            continue
        # 濾掉一小時的合輯跟 30 秒的片段——電台要的是單曲
        if not (60 <= d <= 600):
            continue
        out.append({'title': title, 'id': vid, 'query': f'https://www.youtube.com/watch?v={vid}'})
    return out


def _extend(category, n_seeds=3):
    """抓幾個種子補進池子。**在背景執行**，不擋播放。"""
    seeds = SEEDS.get(category) or []
    if not seeds:
        return
    added = 0
    for _ in range(n_seeds):
        with _lock:
            idx = _seed_cursor.get(category, 0)
            _seed_cursor[category] = (idx + 1) % len(seeds)
        songs = _fetch_seed(seeds[idx])
        with _lock:
            have = {s['id'] for s in _pool.get(category, [])}
            fresh = [s for s in songs if s['id'] not in have]
            _pool.setdefault(category, []).extend(fresh)
            added += len(fresh)
    return added


def _ensure_filling(category):
    """池子快見底時在背景補。同一個分類同時只會有一個補給執行緒。"""
    with _lock:
        if category in _filling:
            return
        _filling.add(category)

    def worker():
        try:
            _extend(category)
        finally:
            with _lock:
                _filling.discard(category)

    threading.Thread(target=worker, daemon=True).start()


def pool_size(category):
    with _lock:
        return len(_pool.get(category, []))


def pick(category, exclude_ids=None, exclude_title_keys=None, normalize=None):
    """挑一首沒播過的。

    `exclude_ids` / `exclude_title_keys` 是 12 小時歷史（軟性排除）；
    `_session_played` 是這次播放期間（**硬性排除，不會退讓**）。

    池子不夠時會**同步**抓一次（第一次啟動時會等幾秒），之後都靠背景補。
    """
    exclude_ids = exclude_ids or set()
    exclude_title_keys = exclude_title_keys or set()

    for attempt in range(3):
        with _lock:
            pool = list(_pool.get(category, []))
            session = set(_session_played)

        def ok(s, strict=True):
            if s['id'] in session:
                return False
            key = normalize(s['title']) if normalize else None
            if key and key in session:
                return False
            if not strict:
                return True
            return s['id'] not in exclude_ids and (not key or key not in exclude_title_keys)

        # 先找「連 12 小時歷史都沒播過」的，找不到才放寬到「只要這次沒播過」
        choices = [s for s in pool if ok(s, True)] or [s for s in pool if ok(s, False)]
        if choices:
            song = random.choice(choices)
            with _lock:
                _session_played.add(song['id'])
                if normalize:
                    k = normalize(song['title'])
                    if k:
                        _session_played.add(k)
            if len(pool) - len(session) < MIN_POOL:
                _ensure_filling(category)
            return song

        # 池子被挑光了 -> 同步補一批再試
        _extend(category, n_seeds=4 if attempt else 2)
    return None


def reset_session():
    """電台停止時呼叫。**只清這次的紀錄，池子留著**——下次啟動就不用重抓。

    這正好對應使用者的要求：一次播放期間不重複，停了之後下次有少部分重複沒關係。
    """
    with _lock:
        _session_played.clear()


def session_count():
    """這次播放期間播了幾首（含標題 key，所以除以 2 才是概數）。"""
    with _lock:
        return len(_session_played)


def warmup(category):
    """先抓一批，讓第一首不用等。可以在啟動電台時呼叫。"""
    if pool_size(category) < MIN_POOL:
        _ensure_filling(category)
