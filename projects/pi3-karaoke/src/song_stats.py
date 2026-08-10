#!/usr/bin/env python3
"""每個人的點歌統計——用來做「常點歌曲」快捷點歌。

## 為什麼要另外存

原本的 `karaoke._history` 是**記憶體裡的 list、只留 12 小時**，服務一重啟就沒了。
它的用途是「短期內別重複播」，不是長期統計，兩者需求不同：

    _history      12 小時、記憶體、給去重用
    song_stats    永久、SQLite、給「這個人常點什麼」用

所以不改動 `_history`，另外開一份。

## 只記「人點的」，不記電台自動播的

電台一小時放十幾首，如果也算進統計，很快就會淹沒真正的點播紀錄。
`record()` 的呼叫端要自己判斷——電台播的不要呼叫。

## 為什麼用「正規化標題」當 key 而不是原始查詢字串

同一首歌可能被點成「稻香」「周杰倫 稻香」「周杰倫-稻香」，
用原始字串會被算成三首不同的歌。正規化之後才會正確累加。
正規化函式由呼叫端傳進來（沿用 karaoke._normalize_title，兩邊共用一份邏輯）。
"""
import os
import sqlite3
import threading
import time

DB_PATH = os.path.expanduser('~/karaoke_stats.sqlite')
_lock = threading.RLock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plays (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    requester   TEXT NOT NULL,
    song_key    TEXT NOT NULL,      -- 正規化後的標題，用來合併同一首歌的不同寫法
    title       TEXT,               -- 最近一次的顯示標題
    query       TEXT,               -- 最近一次能用的查詢字串／網址
    video_id    TEXT,
    mode        TEXT,
    played_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plays_req  ON plays(requester);
CREATE INDEX IF NOT EXISTS idx_plays_key  ON plays(song_key);
CREATE INDEX IF NOT EXISTS idx_plays_time ON plays(played_at);
"""


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA)
    return c


def record(requester, title, query, video_id=None, mode='original', normalize=None):
    """記一次點播。**電台自動播的不要呼叫這支。**"""
    if not title and not query:
        return
    key = (normalize(title or query) if normalize else (title or query)) or (title or query)
    with _lock:
        try:
            c = _conn()
            c.execute(
                "INSERT INTO plays(requester, song_key, title, query, video_id, mode, played_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (requester or '匿名', key, title, query, video_id, mode, time.time()))
            c.commit()
            c.close()
        except sqlite3.Error:
            pass          # 統計壞掉不能影響播放


def top_for(requester, limit=10):
    """某個人最常點的歌。回傳 [{title, query, n, last_at}]，依次數排序。"""
    with _lock:
        try:
            c = _conn()
            rows = c.execute(
                """SELECT song_key,
                          COUNT(*)      AS n,
                          MAX(played_at) AS last_at,
                          -- 顯示用的標題/查詢取「最近一次」的，因為同一首歌
                          -- 早期可能是用關鍵字點的、後來變成精確網址
                          (SELECT title FROM plays p2 WHERE p2.song_key = p1.song_key
                            ORDER BY played_at DESC LIMIT 1) AS title,
                          (SELECT query FROM plays p3 WHERE p3.song_key = p1.song_key
                            ORDER BY played_at DESC LIMIT 1) AS query
                     FROM plays p1
                    WHERE requester = ?
                 GROUP BY song_key
                 ORDER BY n DESC, last_at DESC
                    LIMIT ?""", (requester, limit)).fetchall()
            c.close()
            return [dict(r) for r in rows]
        except sqlite3.Error:
            return []


def top_overall(limit=10, days=None):
    """全場最常點的歌。`days` 給定時只看最近幾天。"""
    with _lock:
        try:
            c = _conn()
            if days:
                rows = c.execute(
                    """SELECT song_key, COUNT(*) n, MAX(played_at) last_at,
                              (SELECT title FROM plays p2 WHERE p2.song_key=p1.song_key
                                ORDER BY played_at DESC LIMIT 1) title,
                              (SELECT query FROM plays p3 WHERE p3.song_key=p1.song_key
                                ORDER BY played_at DESC LIMIT 1) query
                         FROM plays p1 WHERE played_at > ?
                     GROUP BY song_key ORDER BY n DESC, last_at DESC LIMIT ?""",
                    (time.time() - days * 86400, limit)).fetchall()
            else:
                rows = c.execute(
                    """SELECT song_key, COUNT(*) n, MAX(played_at) last_at,
                              (SELECT title FROM plays p2 WHERE p2.song_key=p1.song_key
                                ORDER BY played_at DESC LIMIT 1) title,
                              (SELECT query FROM plays p3 WHERE p3.song_key=p1.song_key
                                ORDER BY played_at DESC LIMIT 1) query
                         FROM plays p1
                     GROUP BY song_key ORDER BY n DESC, last_at DESC LIMIT ?""",
                    (limit,)).fetchall()
            c.close()
            return [dict(r) for r in rows]
        except sqlite3.Error:
            return []


def requesters(limit=20):
    """有點過歌的人，依點播次數排序。"""
    with _lock:
        try:
            c = _conn()
            rows = c.execute(
                "SELECT requester, COUNT(*) n, MAX(played_at) last_at FROM plays"
                " GROUP BY requester ORDER BY n DESC LIMIT ?", (limit,)).fetchall()
            c.close()
            return [dict(r) for r in rows]
        except sqlite3.Error:
            return []


def stats():
    with _lock:
        try:
            c = _conn()
            r = c.execute("SELECT COUNT(*) n, COUNT(DISTINCT song_key) songs,"
                          " COUNT(DISTINCT requester) people FROM plays").fetchone()
            c.close()
            return dict(r)
        except sqlite3.Error:
            return {'n': 0, 'songs': 0, 'people': 0}
