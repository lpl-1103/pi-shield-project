#!/usr/bin/env python3
"""
點歌佇列引擎：管理排隊、播放（透過 mpv + yt-dlp）、原聲/伴奏切換、歌詞同步。

跟 LINE / 網頁前端都無關，純粹是後端狀態機，被 line_control.py import 使用。
"""

from __future__ import annotations

import json
import os
import random
import re
import socket
import subprocess
import threading
import time
import uuid

import requests

MPV_SOCKET = '/tmp/mpv_karaoke_socket'
MPV_LOG_PATH = '/tmp/mpv_karaoke.log'
LRCLIB_SEARCH_URL = 'https://lrclib.net/api/search'


def _detect_headphone_card(fallback=1):
    """
    ALSA 的卡編號在重開機後不保證固定（實測發生過 wm8960soundcard 跟
    bcm2835 Headphones 互換編號），所以不能寫死卡號，要動態從
    /proc/asound/cards 找出真正對應「Pi 4 內建耳機孔」(bcm2835 Headphones)
    的卡號，耳機/喇叭實際接在這裡，不是接在 WM8960 音效板上。
    """
    try:
        with open('/proc/asound/cards', 'r') as f:
            content = f.read()
        for line in content.splitlines():
            m = re.match(r'\s*(\d+)\s*\[(\S+)\s*\]', line)
            if m and 'Headphones' in line:
                return int(m.group(1))
    except OSError:
        pass
    return fallback


HEADPHONE_CARD = _detect_headphone_card()
AUDIO_DEVICE = f'alsa/hw:{HEADPHONE_CARD},0'
DEFAULT_VOLUME_DB = '-1000'  # -10dB，使用者指定的音量偏好


def _apply_default_volume():
    """
    每次程式啟動都主動設定音量，不依賴 ALSA 系統層的存檔/還原機制——
    這台機器上 WM8960 的開機腳本 (wm8960-soundcard.service) 每次開機都會
    覆蓋掉 /var/lib/alsa/asound.state，用 alsactl store 存的音量設定留不住。
    """
    try:
        subprocess.run(
            ['amixer', '-c', str(HEADPHONE_CARD), 'sset', 'PCM', '--', DEFAULT_VOLUME_DB],
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass

# ---------- 熱門歌曲清單（隨機連續播放用） ----------
POPULAR_SONGS = {
    'kpop': [
        'BTS Dynamite', 'BLACKPINK How You Like That', 'NewJeans Super Shy',
        'IVE LOVE DIVE', 'LE SSERAFIM Perfect Night', 'TWICE Fancy',
        'Stray Kids S-Class', 'SEVENTEEN Super', '(G)I-DLE Tomboy',
        'aespa Spicy', 'BTS Butter', 'BIGBANG Bang Bang Bang',
    ],
    'cpop': [
        '周杰倫 稻香', '周杰倫 告白氣球', '五月天 倔強', '五月天 溫柔',
        '林俊傑 江南', '陳奕迅 富士山下', '鄧紫棋 光年之外', '蔡依林 日不落',
        '張惠妹 聽海', '孫燕姿 遇見', '周杰倫 晴天', '王力宏 唯一',
    ],
    'epop': [
        'Ed Sheeran Shape of You', 'Taylor Swift Shake It Off',
        'The Weeknd Blinding Lights', 'Dua Lipa Levitating',
        'Bruno Mars Uptown Funk', 'Justin Bieber Sorry',
        'Ariana Grande 7 rings', 'Adele Rolling in the Deep',
        'Katy Perry Roar', 'Maroon 5 Sugar', 'Charlie Puth Attention',
        'Olivia Rodrigo drivers license',
    ],
}

CATEGORY_LABELS = {'kpop': 'K-pop', 'cpop': '中文流行', 'epop': '英文流行'}

_radio_category = None  # None 或 POPULAR_SONGS 的其中一個 key


class Song:
    def __init__(self, query, requester='匿名', mode='original'):
        self.id = uuid.uuid4().hex[:8]
        self.query = query
        self.requester = requester
        self.mode = mode  # 'original' or 'instrumental'
        self.title = None
        self.added_at = time.time()

    def to_dict(self):
        return {
            'id': self.id,
            'query': self.query,
            'requester': self.requester,
            'mode': self.mode,
            'title': self.title or self.query,
        }


_lock = threading.RLock()
_queue: list[Song] = []
_now_playing: Song | None = None
_mpv_process = None
_lyrics_cache: dict = {}

_history: list = []  # 已播歌曲，依播放先後順序 append（最舊的在最前面），最新的在最後面
_HISTORY_MAX = 500  # 安全上限，避免真的異常長時間沒清到時無限成長；正常情況下靠下面的 TTL 就會控制在很小的數字
_HISTORY_TTL = 12 * 3600  # 12 小時前的播放紀錄視為過期：釋放記憶體，也讓那些歌重新變成「可以再被選到」


def _prune_expired_history():
    """把超過 12 小時的播放紀錄丟掉。_history 是依播放時間遞增 append 的，所以只要從最舊的開始丟，
    丟到第一筆還沒過期的就可以停了，不用整份掃過一遍。"""
    cutoff = time.time() - _HISTORY_TTL
    while _history and _history[0]['played_at'] < cutoff:
        _history.pop(0)


def _record_history(song, video_id, url):
    with _lock:
        _prune_expired_history()
        _history.append({
            'title': song.title,
            'query': song.query,
            'video_id': video_id,
            'url': url,
            'mode': song.mode,
            'requester': song.requester,
            'played_at': time.time(),
        })
        if len(_history) > _HISTORY_MAX:
            _history.pop(0)


def get_history(limit=20):
    with _lock:
        _prune_expired_history()
        return list(reversed(_history[-limit:]))


def get_played_video_ids():
    """12 小時內播過的 YouTube 影片 ID——同一部影片的精確比對，給推薦/電台排除用。"""
    with _lock:
        _prune_expired_history()
        return {h['video_id'] for h in _history if h.get('video_id')}


def get_played_queries():
    """12 小時內播過的原始查詢字串（例如熱門電台清單裡的『周杰倫 稻香』）——給熱門電台選歌避免短期內重複用。"""
    with _lock:
        _prune_expired_history()
        return {h['query'] for h in _history if h.get('query')}


_NOISE_WORDS_RE = re.compile(
    r'official\s*(music\s*)?video|official\s*audio|official\s*mv|\bmv\b|'
    r'lyric[s]?\s*video|\bhd\b|\bhq\b|高清|官方|完整版|full\s*version|Official',
    re.IGNORECASE,
)
_BRACKET_CHARS_RE = re.compile(r'[()\[\]【】{}]')
_NON_ALNUM_RE = re.compile(r'[^\w一-鿿]+')
_CJK_RE = re.compile(r'[一-鿿]+')


def _normalize_title(title):
    """把 YouTube 標題正規化成『是不是同一首歌』的比對 key。不是精準的模糊比對，
    但足以抓住『同一首歌被不同人上傳、標題長得不太一樣』這種常見重複：
    先拿掉常見的宣傳雜訊詞跟括號符號（但保留括號裡的文字，因為很多標題把歌名放在括號裡，
    例如『周杰倫【稻香】』），中文歌名通常會原封不動出現在標題裡，所以優先取中文字元當 key
    （比整串比對穩，不受前後的英文/羅馬拼音/頻道名影響）；沒有中文字的話（英美韓文歌名）
    才退回用整串英數字比對。"""
    if not title:
        return ''
    t = _NOISE_WORDS_RE.sub(' ', title)
    t = _BRACKET_CHARS_RE.sub(' ', t)
    cjk = ''.join(_CJK_RE.findall(t))
    if cjk:
        return cjk
    return _NON_ALNUM_RE.sub('', t.lower())


def get_played_title_keys():
    """12 小時內播過的標題正規化 key 集合——給推薦功能排除『同一首歌、不同影片版本』用。"""
    with _lock:
        _prune_expired_history()
        return {_normalize_title(h['title']) for h in _history if h.get('title')}


def _resolve_youtube(query, mode):
    """回傳 (title, watch_url)，解析失敗回傳 (None, None)。"""
    is_url = query.startswith(('http://', 'https://'))
    if is_url:
        target = query
    else:
        search_text = f'{query} 伴奏 instrumental' if mode == 'instrumental' else query
        target = f'ytsearch1:{search_text}'
    try:
        result = subprocess.run(
            ['yt-dlp', '--print', '%(title)s', '--print', '%(id)s', target],
            capture_output=True, text=True, timeout=25,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None, None
    lines = result.stdout.strip().splitlines()
    if len(lines) < 2:
        return None, None
    title, video_id = lines[0], lines[1]
    return title, f'https://www.youtube.com/watch?v={video_id}'


def search_top_songs(keyword, count=5, exclude_ids=None, exclude_title_keys=None):
    """
    給歌手名/關鍵字，回傳最多 count 首搜尋結果 [{'title':..., 'id':...}, ...]。
    排除兩種「已經播過」：exclude_ids 是精確的影片 ID 比對；exclude_title_keys 是
    _normalize_title() 正規化過的標題 key，用來抓「同一首歌、不同人上傳/不同影片 ID」
    這種光比對 ID 抓不到的重複（例如同一首歌的官方版跟另一個頻道的翻唱/合輯裡都有收錄）。
    用 --flat-playlist 只列基本資訊，不逐一解析播放格式，回應快很多。
    這是「YouTube 搜尋排序」不是正式排行榜資料，但對熱門歌手夠準了。
    """
    exclude_ids = exclude_ids or set()
    exclude_title_keys = exclude_title_keys or set()
    # 多抓一點候選，扣掉已播過的之後才有機會湊滿 count 首
    fetch_count = count + len(exclude_ids) + 5
    target = f'ytsearch{fetch_count}:{keyword} 熱門歌曲'
    try:
        result = subprocess.run(
            ['yt-dlp', '--flat-playlist', '--print', '%(title)s', '--print', '%(id)s', target],
            capture_output=True, text=True, timeout=25,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    lines = result.stdout.strip().splitlines()
    songs = []
    seen_title_keys = set()
    for i in range(0, len(lines) - 1, 2):
        title, video_id = lines[i], lines[i + 1]
        if video_id in exclude_ids:
            continue
        title_key = _normalize_title(title)
        if title_key and (title_key in exclude_title_keys or title_key in seen_title_keys):
            continue
        seen_title_keys.add(title_key)
        songs.append({'title': title, 'id': video_id})
        if len(songs) >= count:
            break
    return songs


def _mpv_query(prop):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            sock.connect(MPV_SOCKET)
            sock.sendall(json.dumps({'command': ['get_property', prop]}).encode() + b'\n')
            data = sock.recv(4096)
            for line in data.decode('utf-8', errors='ignore').splitlines():
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if 'data' in obj:
                    return obj['data']
    except OSError:
        return None
    return None


def _pick_radio_song(category):
    """從熱門清單裡挑一首，排除 12 小時內播過的（不管是電台自己播的還是使用者點播的）。
    如果整個分類（目前每類只有 12 首）都在 12 小時內播過了，才會退回允許重複——
    這是清單本來就小、遲早會繞回來的必然結果，不是 bug。"""
    pool = POPULAR_SONGS[category]
    played = get_played_queries()
    choices = [s for s in pool if s not in played] or pool
    return random.choice(choices)


def start_radio(category):
    global _radio_category
    if category not in POPULAR_SONGS:
        return False
    with _lock:
        _radio_category = category
    return True


def stop_radio():
    global _radio_category
    with _lock:
        _radio_category = None
    skip()


def get_radio_category():
    with _lock:
        return _radio_category


def _player_loop():
    global _now_playing, _mpv_process
    while True:
        with _lock:
            if _now_playing is None and not _queue and _radio_category:
                label = CATEGORY_LABELS[_radio_category]
                _queue.append(Song(_pick_radio_song(_radio_category), f'🔀 熱門播放（{label}）', 'original'))
            if _now_playing is None and _queue:
                _now_playing = _queue.pop(0)
        if _now_playing is None:
            time.sleep(1)
            continue

        song = _now_playing
        title, url = _resolve_youtube(song.query, song.mode)
        if url is None:
            with _lock:
                _now_playing = None
            continue
        song.title = title
        video_id = url.rsplit('v=', 1)[-1] if url else None
        _record_history(song, video_id, url)

        if os.path.exists(MPV_SOCKET):
            os.remove(MPV_SOCKET)

        cmd = [
            'mpv', '--no-video', '--ao=alsa', f'--audio-device={AUDIO_DEVICE}',
            f'--input-ipc-server={MPV_SOCKET}',
            '--quiet',
            url,
        ]
        # 之前是 --really-quiet + DEVNULL，播放失敗時完全看不到 mpv 的錯誤訊息。
        # --quiet 只關掉逐秒進度列，警告/錯誤還是會印出來，寫進這個檔案方便事後查。
        with open(MPV_LOG_PATH, 'w') as log_file:
            proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
            with _lock:
                _mpv_process = proc

            proc.wait()

        with _lock:
            _mpv_process = None
            _now_playing = None


def start():
    _apply_default_volume()
    threading.Thread(target=_player_loop, daemon=True).start()


def add_song(query, requester='匿名', mode='original'):
    song = Song(query, requester, mode)
    with _lock:
        _queue.append(song)
    return song


def remove_song(song_id):
    with _lock:
        global _queue
        _queue = [s for s in _queue if s.id != song_id]


def move_to_front(song_id):
    with _lock:
        song = next((s for s in _queue if s.id == song_id), None)
        if song:
            _queue.remove(song)
            _queue.insert(0, song)
    return song is not None


def skip():
    with _lock:
        proc = _mpv_process
    if proc is not None:
        proc.terminate()


def stop_all():
    with _lock:
        _queue.clear()
    skip()


def switch_mode(new_mode):
    with _lock:
        current = _now_playing
        if current is None:
            return False
        new_song = Song(current.query, current.requester, new_mode)
        _queue.insert(0, new_song)
    skip()
    return True


def get_status():
    with _lock:
        now = _now_playing.to_dict() if _now_playing else None
        q = [s.to_dict() for s in _queue]
    time_pos = None
    duration = None
    if now is not None:
        time_pos = _mpv_query('time-pos')
        duration = _mpv_query('duration')
    return {
        'now_playing': now,
        'time_pos': time_pos,
        'duration': duration,
        'queue': q,
        'radio_category': _radio_category,
    }


_LRC_LINE = re.compile(r'\[(\d+):(\d+(?:\.\d+)?)\](.*)')
# 有些 lrclib 的同步歌詞是「逐字歌詞」格式，行內每個字前面還會插一個
# <mm:ss.xxx> 時間標記（給逐字高亮用），例如 <00:00.000>青<00:00.366>花...
# 不是每首歌都有這種格式，但只要有，之前完全沒處理，這些標記就會被當成
# 歌詞文字整段顯示出來。這裡把行內的這種標記濾掉，只留下真正的歌詞文字。
_LRC_INLINE_TAG = re.compile(r'<\d+:\d+(?:\.\d+)?>')


def _parse_lrc(lrc_text):
    lines = []
    for raw_line in lrc_text.splitlines():
        m = _LRC_LINE.match(raw_line)
        if not m:
            continue
        minutes, seconds, text = m.groups()
        t = int(minutes) * 60 + float(seconds)
        text = _LRC_INLINE_TAG.sub('', text).strip()
        if text:
            lines.append({'time': t, 'text': text})
    lines.sort(key=lambda x: x['time'])
    return lines


def _search_lyrics_once(search_text):
    try:
        resp = requests.get(LRCLIB_SEARCH_URL, params={'q': search_text}, timeout=8)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    for item in resp.json():
        synced = item.get('syncedLyrics')
        if synced:
            return _parse_lrc(synced)
    return None


def fetch_lyrics(*search_terms):
    """依序嘗試每個搜尋字（例如先用使用者輸入的乾淨歌名，再用 YouTube 標題當備援）。"""
    search_terms = [t for t in search_terms if t]
    if not search_terms:
        return None
    cache_key = '|'.join(search_terms)
    if cache_key in _lyrics_cache:
        return _lyrics_cache[cache_key]
    lyrics = None
    for term in search_terms:
        lyrics = _search_lyrics_once(term)
        if lyrics:
            break
    _lyrics_cache[cache_key] = lyrics
    return lyrics
