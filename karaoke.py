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
LRCLIB_SEARCH_URL = 'https://lrclib.net/api/search'
AUDIO_DEVICE = 'alsa/hw:1,0'  # Pi 4 內建耳機孔，不是 WM8960 音效板

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
_radio_recent: list = []  # 避免短期內重複選到同一首


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
    except subprocess.TimeoutExpired:
        return None, None
    lines = result.stdout.strip().splitlines()
    if len(lines) < 2:
        return None, None
    title, video_id = lines[0], lines[1]
    return title, f'https://www.youtube.com/watch?v={video_id}'


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
    pool = POPULAR_SONGS[category]
    choices = [s for s in pool if s not in _radio_recent[-5:]] or pool
    pick = random.choice(choices)
    _radio_recent.append(pick)
    if len(_radio_recent) > 10:
        _radio_recent.pop(0)
    return pick


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

        if os.path.exists(MPV_SOCKET):
            os.remove(MPV_SOCKET)

        cmd = [
            'mpv', '--no-video', '--ao=alsa', f'--audio-device={AUDIO_DEVICE}',
            f'--input-ipc-server={MPV_SOCKET}',
            '--really-quiet',
            url,
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with _lock:
            _mpv_process = proc

        proc.wait()

        with _lock:
            _mpv_process = None
            _now_playing = None


def start():
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


def _parse_lrc(lrc_text):
    lines = []
    for raw_line in lrc_text.splitlines():
        m = _LRC_LINE.match(raw_line)
        if not m:
            continue
        minutes, seconds, text = m.groups()
        t = int(minutes) * 60 + float(seconds)
        text = text.strip()
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
