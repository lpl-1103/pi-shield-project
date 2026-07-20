#!/usr/bin/env python3
"""
Pi3 Shield LINE Bot 控制程式

接收 LINE Messaging API 的 Webhook 訊息，用文字指令觸發硬體動作。
指令跟鍵盤版 (pi3_control.py) 用同一套按鍵字元，對照表見 pi3_control.md。

需要 pi3_line_config.json（同目錄下）提供 channel_secret / channel_access_token。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading

import requests
from flask import Flask, abort, jsonify, request

import karaoke
from pi3_control import NOTE_KEYS, PAINTER_SONG, Pi3Shield

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pi3_line_config.json')

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    _config = json.load(f)

CHANNEL_SECRET = _config['channel_secret']
CHANNEL_ACCESS_TOKEN = _config['channel_access_token']

LINE_REPLY_URL = 'https://api.line.me/v2/bot/message/reply'

# 網頁面板用的數字 -> 音符對照（跟鍵盤版的 q/w/e/r/t 字母對照分開，互不影響）
NOTE_NUMBER_MAP = {
    '1': 'do', '2': 're', '3': 'mi', '4': 'fa',
    '5': 'so', '6': 'la', '7': 'xi',
}

MENU_TEXT = (
    "Pi3 Shield 指令列表\n"
    "燈泡: 1=燈泡1長亮 2=燈泡2長亮 3=一起長亮\n"
    "      4=燈泡1閃爍 5=燈泡2閃爍 6=一起閃爍  0=全部熄滅\n"
    "蜂鳴器: q=Do w=Re e=Mi r=Fa t=So  p=播放粉刷匠\n"
    "繼電器: o=開啟 k=關閉\n"
    "help = 顯示這個列表\n"
    "面板 = 傳送可點擊的圖形控制面板連結\n"
    "\n"
    "點歌系統（詳見操作手冊）：\n"
    "  點歌 <歌名>       = 加入排隊（尾綴0=伴奏版，例如「點歌 小星星0」）\n"
    "  排隊              = 查看目前播放/排隊列表\n"
    "  切歌 / 刪除 <編號> / 頂歌 <編號>\n"
    "  原聲 / 伴奏        = 切換目前播放的版本\n"
    "  停止              = 停止播放並清空排隊\n"
    "  熱門 kpop/中文/英文 = 隨機連續播放熱門歌曲，直到「暫停熱門」\n"
    "  小樂小樂，我要點歌 = 傳送點歌頁面連結+操作手冊"
)

PANEL_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
<title>Pi3 Shield 控制面板</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f2f3f7;
    --card: #ffffff;
    --text: #1c1c1e;
    --sub: #6b6b70;
    --accent: #0078d4;
    --accent2: #ff9500;
    --accent3: #34c759;
    --danger: #ff3b30;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0e0e10;
      --card: #1c1c1e;
      --text: #f2f2f7;
      --sub: #9a9a9e;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 20px 16px 40px;
    max-width: 480px;
    margin: 0 auto;
  }
  h1 {
    font-size: 20px;
    text-align: center;
    margin: 8px 0 20px;
  }
  .view { display: none; }
  .view.active { display: block; }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }
  .grid.single { grid-template-columns: 1fr; }
  .card {
    background: var(--card);
    border-radius: 16px;
    padding: 22px 12px;
    text-align: center;
    border: none;
    box-shadow: 0 2px 10px rgba(0,0,0,.08);
    font-size: 17px;
    font-weight: 600;
    color: var(--text);
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }
  .card:active { transform: scale(0.97); }
  .card .emoji { display: block; font-size: 34px; margin-bottom: 8px; }
  .btn {
    width: 100%;
    padding: 16px 10px;
    border-radius: 14px;
    border: none;
    font-size: 16px;
    font-weight: 600;
    color: #fff;
    background: var(--accent);
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }
  .btn:active { opacity: .8; }
  .btn.orange { background: var(--accent2); }
  .btn.green { background: var(--accent3); }
  .btn.red { background: var(--danger); }
  .btn.gray { background: #8e8e93; }
  .back {
    display: inline-block;
    margin-bottom: 16px;
    color: var(--accent);
    font-size: 16px;
    font-weight: 600;
    background: none;
    border: none;
    padding: 6px 0;
    cursor: pointer;
  }
  .section-title {
    font-size: 14px;
    color: var(--sub);
    margin: 20px 0 10px;
    font-weight: 600;
  }
  .note-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
  }
  .note-btn {
    aspect-ratio: 1;
    border-radius: 14px;
    border: none;
    background: var(--card);
    box-shadow: 0 2px 8px rgba(0,0,0,.08);
    color: var(--text);
    font-size: 15px;
    font-weight: 700;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    cursor: pointer;
  }
  .note-btn:active { transform: scale(0.95); }
  .note-btn .num { font-size: 20px; color: var(--accent); }
  .status {
    position: fixed;
    left: 16px;
    right: 16px;
    bottom: 16px;
    max-width: 448px;
    margin: 0 auto;
    background: var(--card);
    color: var(--text);
    padding: 12px 16px;
    border-radius: 12px;
    box-shadow: 0 4px 16px rgba(0,0,0,.18);
    font-size: 14px;
    text-align: center;
    opacity: 0;
    transition: opacity .2s;
    pointer-events: none;
  }
  .status.show { opacity: 1; }
</style>
</head>
<body>
  <h1>🔧 Pi3 Shield 控制面板</h1>

  <div id="view-home" class="view active">
    <div class="grid">
      <button class="card" onclick="showView('led')"><span class="emoji">💡</span>燈泡</button>
      <button class="card" onclick="showView('buzzer')"><span class="emoji">🎵</span>蜂鳴器</button>
      <button class="card" onclick="showView('other')"><span class="emoji">🔌</span>其他 (繼電器)</button>
    </div>
  </div>

  <div id="view-led" class="view">
    <button class="back" onclick="showView('home')">‹ 返回</button>
    <div class="section-title">長亮</div>
    <div class="grid">
      <button class="btn" onclick="callLed('steady1', '燈泡1 長亮')">燈泡1</button>
      <button class="btn" onclick="callLed('steady2', '燈泡2 長亮')">燈泡2</button>
    </div>
    <div class="grid single" style="margin-top:10px">
      <button class="btn green" onclick="callLed('steady_both', '燈泡1+2 一起長亮')">兩個一起長亮</button>
    </div>
    <div class="section-title">閃爍</div>
    <div class="grid">
      <button class="btn orange" onclick="callLed('blink1', '燈泡1 閃爍中')">燈泡1</button>
      <button class="btn orange" onclick="callLed('blink2', '燈泡2 閃爍中')">燈泡2</button>
    </div>
    <div class="grid single" style="margin-top:10px">
      <button class="btn orange" onclick="callLed('blink_both', '燈泡1+2 一起閃爍中')">兩個一起閃爍</button>
    </div>
    <div class="section-title">&nbsp;</div>
    <div class="grid single">
      <button class="btn red" onclick="callLed('off', '燈泡全部熄滅')">全部熄滅</button>
    </div>
  </div>

  <div id="view-buzzer" class="view">
    <button class="back" onclick="showView('home')">‹ 返回</button>
    <div class="section-title">音符</div>
    <div class="note-grid">
      <button class="note-btn" onclick="callNote('do','1')"><span class="num">1</span>Do</button>
      <button class="note-btn" onclick="callNote('re','2')"><span class="num">2</span>Re</button>
      <button class="note-btn" onclick="callNote('mi','3')"><span class="num">3</span>Mi</button>
      <button class="note-btn" onclick="callNote('fa','4')"><span class="num">4</span>Fa</button>
      <button class="note-btn" onclick="callNote('so','5')"><span class="num">5</span>So</button>
      <button class="note-btn" onclick="callNote('la','6')"><span class="num">6</span>La</button>
      <button class="note-btn" onclick="callNote('xi','7')"><span class="num">7</span>Xi</button>
    </div>
    <div class="section-title">一鍵播放</div>
    <div class="grid single">
      <button class="btn orange" onclick="callSong()">🎶 播放《粉刷匠》</button>
    </div>
  </div>

  <div id="view-other" class="view">
    <button class="back" onclick="showView('home')">‹ 返回</button>
    <div class="section-title">繼電器</div>
    <div class="grid">
      <button class="btn green" onclick="callRelay('on', '繼電器 開啟')">開啟 ON</button>
      <button class="btn red" onclick="callRelay('off', '繼電器 關閉')">關閉 OFF</button>
    </div>
  </div>

  <div id="status" class="status"></div>

<script>
function showView(name) {
  document.querySelectorAll('.view').forEach(function (el) { el.classList.remove('active'); });
  document.getElementById('view-' + name).classList.add('active');
}

function showStatus(text) {
  var el = document.getElementById('status');
  el.textContent = text;
  el.classList.add('show');
  clearTimeout(showStatus._t);
  showStatus._t = setTimeout(function () { el.classList.remove('show'); }, 2000);
}

function callApi(url, label) {
  fetch(url).then(function (r) { return r.json(); }).then(function (data) {
    showStatus(data.status === 'ok' ? label : ('錯誤: ' + data.message));
  }).catch(function () {
    showStatus('連線失敗，請確認樹莓派是否開機');
  });
}

function callLed(action, label) {
  callApi('/api/led?action=' + action, label);
}

function callNote(name, num) {
  callApi('/api/note?name=' + name, '播放音符 ' + num + ' (' + name.toUpperCase() + ')');
}

function callSong() {
  callApi('/api/song', '開始播放《粉刷匠》🎵');
}

function callRelay(action, label) {
  callApi('/api/relay?action=' + action, label);
}
</script>
</body>
</html>
"""

KARAOKE_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
<title>🎤 點歌系統</title>
<style>
  :root {
    color-scheme: light dark;
    --bg-a: #eef0ff;
    --bg-b: #fbe8f5;
    --bg-c: #e6f4ff;
    --card: rgba(255,255,255,.68);
    --card-solid: #ffffff;
    --card-border: rgba(255,255,255,.6);
    --text: #1c1a2b;
    --sub: #726f8c;
    --shadow: 0 10px 30px rgba(90,70,150,.12);
    --brand: linear-gradient(135deg, #7c6ff5, #ff6fa0);
    --brand2: linear-gradient(135deg, #06b6d4, #22c55e);
    --danger: #ff3b30;
    --track: rgba(120,110,160,.18);
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg-a: #120e22; --bg-b: #1c1030; --bg-c: #0d1b2b;
      --card: rgba(30,26,48,.58); --card-solid: #241f3b; --card-border: rgba(255,255,255,.08);
      --text: #f3f1ff; --sub: #a79fc9;
      --shadow: 0 10px 30px rgba(0,0,0,.45);
      --track: rgba(255,255,255,.12);
    }
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html { scrollbar-width: none; }
  body {
    margin: 0;
    min-height: 100vh;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif;
    color: var(--text);
    padding: 22px 16px 60px;
    max-width: 480px;
    margin: 0 auto;
    background:
      radial-gradient(circle at 12% 8%, var(--bg-b) 0%, transparent 45%),
      radial-gradient(circle at 90% 15%, var(--bg-c) 0%, transparent 40%),
      radial-gradient(circle at 50% 100%, var(--bg-b) 0%, transparent 50%),
      var(--bg-a);
    background-attachment: fixed;
  }
  .topbar { text-align: center; margin-bottom: 20px; }
  .topbar .kicker {
    font-size: 11px; letter-spacing: .18em; text-transform: uppercase;
    color: var(--sub); font-weight: 700;
  }
  .topbar h1 {
    font-size: 24px; margin: 4px 0 0; font-weight: 800; letter-spacing: -.01em;
    background: var(--brand);
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }
  .card {
    background: var(--card);
    backdrop-filter: blur(22px) saturate(160%);
    -webkit-backdrop-filter: blur(22px) saturate(160%);
    border: 1px solid var(--card-border);
    border-radius: 24px;
    padding: 20px;
    margin-bottom: 16px;
    box-shadow: var(--shadow);
  }
  .dim { color: var(--sub); font-weight: 400; }
  .section-title {
    font-size: 12px; color: var(--sub); font-weight: 800; margin-bottom: 12px;
    text-transform: uppercase; letter-spacing: .1em;
    display: flex; align-items: center; gap: 6px;
  }

  /* ---- Now playing ---- */
  .np-head { display: flex; align-items: center; gap: 14px; }
  .vinyl {
    width: 64px; height: 64px; border-radius: 50%; flex-shrink: 0;
    background: conic-gradient(from 0deg, #7c6ff5, #ff6fa0, #ffb86f, #7c6ff5);
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 6px 18px rgba(124,111,245,.4);
  }
  .vinyl::after { content: ''; width: 24px; height: 24px; border-radius: 50%; background: var(--card-solid); }
  .vinyl.spinning { animation: spin 5s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .np-info { min-width: 0; flex: 1; }
  .np-title {
    font-size: 17px; font-weight: 800; line-height: 1.3;
    overflow: hidden; text-overflow: ellipsis; display: -webkit-box;
    -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  }
  .np-sub { font-size: 12.5px; color: var(--sub); margin-top: 5px; }
  .pill {
    display: inline-block; padding: 2px 9px; border-radius: 999px;
    font-size: 11px; font-weight: 700; color: #fff; background: var(--brand);
    margin-right: 5px;
  }
  .pill.alt { background: var(--brand2); }
  .progress-track {
    background: var(--track);
    border-radius: 8px; height: 7px; margin-top: 16px; overflow: hidden;
  }
  .progress-bar { background: var(--brand); height: 100%; width: 0%; border-radius: 8px; transition: width .3s linear; }
  .progress-time { font-size: 11px; color: var(--sub); margin-top: 7px; text-align: right; font-variant-numeric: tabular-nums; }
  .np-actions { display: flex; gap: 8px; margin-top: 16px; }
  .btn {
    flex: 1; padding: 13px 8px; border-radius: 16px; border: none;
    font-size: 13.5px; font-weight: 700; color: #fff; background: var(--brand);
    cursor: pointer; transition: transform .12s, opacity .12s;
  }
  .btn:active { transform: scale(.95); opacity: .85; }
  .btn.alt { background: var(--brand2); }
  .btn.ghost {
    background: rgba(120,110,160,.14); color: var(--text);
  }

  /* ---- Lyrics ---- */
  .lyrics-box {
    min-height: 130px; display: flex; flex-direction: column;
    justify-content: center; gap: 12px; text-align: center;
  }
  .lyric-line { font-size: 14px; color: var(--sub); opacity: .55; transition: all .25s; }
  .lyric-line.current {
    font-size: 20px; font-weight: 800; opacity: 1;
    background: var(--brand);
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }

  /* ---- Radio ---- */
  .radio-status {
    font-size: 12.5px; color: var(--sub); margin-bottom: 12px; min-height: 18px; font-weight: 600;
  }
  .grid-3 { display: flex; gap: 8px; }
  .radio-btn {
    flex: 1; padding: 14px 6px; border-radius: 16px; border: none;
    background: rgba(120,110,160,.12); color: var(--text);
    font-size: 12.5px; font-weight: 800; cursor: pointer;
    transition: transform .12s, box-shadow .2s;
    display: flex; flex-direction: column; align-items: center; gap: 4px;
  }
  .radio-btn .emoji { font-size: 18px; }
  .radio-btn:active { transform: scale(.95); }
  .radio-btn.kpop.active { background: linear-gradient(135deg, #a855f7, #ec4899); color: #fff; box-shadow: 0 8px 18px rgba(168,85,247,.4); }
  .radio-btn.cpop.active { background: linear-gradient(135deg, #f43f5e, #f59e0b); color: #fff; box-shadow: 0 8px 18px rgba(244,63,94,.35); }
  .radio-btn.epop.active { background: linear-gradient(135deg, #3b82f6, #06b6d4); color: #fff; box-shadow: 0 8px 18px rgba(59,130,246,.35); }

  /* ---- Add song ---- */
  .add-row {
    display: flex; align-items: center; gap: 10px;
    background: rgba(120,110,160,.12); border-radius: 16px; padding: 4px 6px 4px 16px;
  }
  .add-row .icon { color: var(--sub); font-size: 15px; }
  .add-row input {
    flex: 1; border: none; background: transparent; color: var(--text);
    font-size: 15px; padding: 12px 4px; outline: none;
  }
  .segmented {
    display: flex; gap: 4px; margin-top: 12px;
    background: rgba(120,110,160,.12); border-radius: 14px; padding: 4px;
  }
  .seg-btn {
    flex: 1; padding: 9px; border-radius: 11px; border: none; background: transparent;
    color: var(--sub); font-size: 13px; font-weight: 700; cursor: pointer; transition: all .2s;
  }
  .seg-btn.active { background: var(--card-solid); color: var(--text); box-shadow: 0 3px 10px rgba(0,0,0,.1); }
  .add-btn {
    margin-top: 12px; width: 100%; padding: 14px; border-radius: 16px; border: none;
    background: var(--brand); color: #fff; font-size: 15px; font-weight: 800; cursor: pointer;
    box-shadow: 0 8px 20px rgba(124,111,245,.35);
    transition: transform .12s;
  }
  .add-btn:active { transform: scale(.97); }

  /* ---- Queue ---- */
  .queue-empty { color: var(--sub); font-size: 13.5px; text-align: center; padding: 14px 0; }
  .queue-item {
    display: flex; align-items: center; gap: 12px;
    padding: 11px 0; border-bottom: 1px solid var(--card-border);
  }
  .queue-item:last-child { border-bottom: none; }
  .queue-num {
    width: 28px; height: 28px; border-radius: 50%; flex-shrink: 0;
    background: var(--brand); color: #fff;
    font-size: 12px; font-weight: 800;
    display: flex; align-items: center; justify-content: center;
  }
  .queue-info { flex: 1; min-width: 0; }
  .queue-title { font-size: 14px; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .queue-sub { font-size: 11.5px; color: var(--sub); margin-top: 2px; }
  .mini-btn {
    border: none; border-radius: 50%; width: 32px; height: 32px; flex-shrink: 0;
    font-size: 13px; font-weight: 700;
    background: rgba(120,110,160,.14); color: var(--text);
    cursor: pointer; transition: transform .12s;
  }
  .mini-btn:active { transform: scale(.9); }
  .mini-btn.danger { background: rgba(255,59,48,.15); color: var(--danger); }
</style>
</head>
<body>
  <div class="topbar">
    <div class="kicker">Pi3 Shield · Live Karaoke</div>
    <h1>🎤 點歌系統</h1>
  </div>

  <div class="card" id="now-playing-card">
    <div class="np-head">
      <div class="vinyl" id="vinyl"></div>
      <div id="now-playing" class="np-info"><div class="np-title dim">目前沒有播放中的歌曲</div></div>
    </div>
    <div class="progress-track"><div class="progress-bar" id="progress-bar"></div></div>
    <div class="progress-time" id="progress-time"></div>
    <div class="np-actions">
      <button class="btn ghost" onclick="skip()">⏭ 切歌</button>
      <button class="btn" onclick="setMode('original')">🎤 原聲</button>
      <button class="btn alt" onclick="setMode('instrumental')">🎹 伴奏</button>
    </div>
  </div>

  <div class="card">
    <div class="section-title">✨ 歌詞</div>
    <div class="lyrics-box" id="lyrics"><div class="lyric-line dim">目前沒有播放</div></div>
  </div>

  <div class="card">
    <div class="section-title">🔥 熱門歌曲・隨機連播</div>
    <div class="radio-status" id="radio-status">目前沒有在隨機播放</div>
    <div class="grid-3">
      <button id="radio-kpop" class="radio-btn kpop" onclick="startRadio('kpop')"><span class="emoji">💜</span>K-pop</button>
      <button id="radio-cpop" class="radio-btn cpop" onclick="startRadio('cpop')"><span class="emoji">🏮</span>中文流行</button>
      <button id="radio-epop" class="radio-btn epop" onclick="startRadio('epop')"><span class="emoji">🎧</span>英文流行</button>
    </div>
    <button class="btn ghost" style="width:100%; margin-top:10px" onclick="stopRadio()">⏸ 暫停熱門播放</button>
  </div>

  <div class="card">
    <div class="section-title">🎶 點歌</div>
    <div class="add-row">
      <span class="icon">🔍</span>
      <input id="song-input" type="text" placeholder="輸入歌名或 YouTube 網址" onkeydown="if(event.key==='Enter')addSong()" />
    </div>
    <div class="segmented">
      <button id="mode-original" class="seg-btn active" onclick="selectMode('original')">🎤 原聲</button>
      <button id="mode-instrumental" class="seg-btn" onclick="selectMode('instrumental')">🎹 伴奏</button>
    </div>
    <button class="add-btn" onclick="addSong()">➕ 加入排隊</button>
  </div>

  <div class="card">
    <div class="section-title">📃 排隊列表</div>
    <div id="queue-list"><div class="queue-empty">排隊中沒有歌曲</div></div>
  </div>

<script>
let selectedMode = 'original';
let currentLyrics = null;
let currentLyricsTitle = null;

function selectMode(mode) {
  selectedMode = mode;
  document.getElementById('mode-original').classList.toggle('active', mode === 'original');
  document.getElementById('mode-instrumental').classList.toggle('active', mode === 'instrumental');
}

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s == null ? '' : s;
  return div.innerHTML;
}

function fmtTime(sec) {
  if (sec == null) return '--:--';
  sec = Math.floor(sec);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m + ':' + String(s).padStart(2, '0');
}

function renderNowPlaying(data) {
  const np = data.now_playing;
  const el = document.getElementById('now-playing');
  const vinyl = document.getElementById('vinyl');
  if (!np) {
    el.innerHTML = '<div class="np-title dim">目前沒有播放中的歌曲</div>';
    document.getElementById('progress-bar').style.width = '0%';
    document.getElementById('progress-time').textContent = '';
    vinyl.classList.remove('spinning');
    return;
  }
  vinyl.classList.add('spinning');
  const modeLabel = np.mode === 'instrumental' ? '伴奏版' : '原聲';
  const pillClass = np.mode === 'instrumental' ? 'pill alt' : 'pill';
  el.innerHTML = '<div class="np-title">' + escapeHtml(np.title) + '</div>' +
    '<div class="np-sub"><span class="' + pillClass + '">' + modeLabel + '</span>' + escapeHtml(np.requester) + '</div>';
  const pct = data.duration ? Math.min(100, (data.time_pos / data.duration) * 100) : 0;
  document.getElementById('progress-bar').style.width = pct + '%';
  document.getElementById('progress-time').textContent = fmtTime(data.time_pos) + ' / ' + fmtTime(data.duration);
}

function renderLyrics(lyrics, timePos) {
  const el = document.getElementById('lyrics');
  if (!lyrics || lyrics.length === 0) {
    el.innerHTML = '<div class="lyric-line dim">（沒有找到歌詞）</div>';
    return;
  }
  let idx = -1;
  for (let i = 0; i < lyrics.length; i++) {
    if (lyrics[i].time <= (timePos || 0)) idx = i; else break;
  }
  const start = Math.max(0, idx - 2);
  const end = Math.min(lyrics.length, idx + 4);
  let html = '';
  for (let i = start; i < end; i++) {
    const cls = i === idx ? 'lyric-line current' : 'lyric-line';
    html += '<div class="' + cls + '">' + escapeHtml(lyrics[i].text) + '</div>';
  }
  el.innerHTML = html;
}

function renderQueue(queue) {
  const el = document.getElementById('queue-list');
  if (!queue || queue.length === 0) {
    el.innerHTML = '<div class="queue-empty">排隊中沒有歌曲</div>';
    return;
  }
  let html = '';
  queue.forEach(function (s, i) {
    const modeLabel = s.mode === 'instrumental' ? '伴奏' : '原聲';
    html += '<div class="queue-item">' +
      '<div class="queue-num">' + (i + 1) + '</div>' +
      '<div class="queue-info"><div class="queue-title">' + escapeHtml(s.query) + '</div>' +
      '<div class="queue-sub">' + modeLabel + ' · ' + escapeHtml(s.requester) + '</div></div>' +
      '<button class="mini-btn" onclick="priority(\\'' + s.id + '\\')">⬆</button>' +
      '<button class="mini-btn danger" onclick="removeSong(\\'' + s.id + '\\')">✕</button>' +
      '</div>';
  });
  el.innerHTML = html;
}

const RADIO_LABELS = {kpop: 'K-pop', cpop: '中文流行', epop: '英文流行'};

function renderRadio(category) {
  const statusEl = document.getElementById('radio-status');
  statusEl.textContent = category ? ('🔀 隨機播放中：' + RADIO_LABELS[category]) : '目前沒有在隨機播放';
  ['kpop', 'cpop', 'epop'].forEach(function (c) {
    document.getElementById('radio-' + c).classList.toggle('active', c === category);
  });
}

function poll() {
  fetch('/api/karaoke/status').then(function (r) { return r.json(); }).then(function (data) {
    renderNowPlaying(data);
    renderQueue(data.queue);
    renderRadio(data.radio_category);
    if (data.now_playing) {
      if (currentLyricsTitle !== data.now_playing.title) {
        currentLyrics = data.lyrics;
        currentLyricsTitle = data.now_playing.title;
      }
      renderLyrics(currentLyrics, data.time_pos);
    } else {
      currentLyrics = null;
      currentLyricsTitle = null;
      document.getElementById('lyrics').innerHTML = '<div class="lyric-line dim">目前沒有播放</div>';
    }
  }).catch(function () {});
}

function startRadio(category) {
  fetch('/api/karaoke/radio', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({category: category})
  }).then(poll);
}

function stopRadio() {
  fetch('/api/karaoke/radio/stop', {method: 'POST'}).then(poll);
}

function addSong() {
  const input = document.getElementById('song-input');
  const query = input.value.trim();
  if (!query) return;
  fetch('/api/karaoke/add', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({query: query, mode: selectedMode, requester: '網頁點歌'})
  }).then(function () { input.value = ''; poll(); });
}

function removeSong(id) {
  fetch('/api/karaoke/remove', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({id: id})
  }).then(poll);
}

function priority(id) {
  fetch('/api/karaoke/priority', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({id: id})
  }).then(poll);
}

function skip() {
  fetch('/api/karaoke/skip', {method: 'POST'}).then(poll);
}

function setMode(mode) {
  fetch('/api/karaoke/mode', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({mode: mode})
  }).then(poll);
}

poll();
setInterval(poll, 1500);
</script>
</body>
</html>
"""

MANUAL_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>點歌系統操作手冊</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f2f3f7; --card: #ffffff; --text: #1c1c1e; --sub: #6b6b70; --accent: #0078d4;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #0e0e10; --card: #1c1c1e; --text: #f2f2f7; --sub: #9a9a9e; }
  }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif;
    background: var(--bg); color: var(--text);
    max-width: 560px; margin: 0 auto; padding: 20px 18px 50px;
    line-height: 1.7;
  }
  h1 { font-size: 22px; }
  h2 { font-size: 17px; margin-top: 28px; color: var(--accent); }
  .card { background: var(--card); border-radius: 14px; padding: 14px 16px; margin: 10px 0; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
  code { background: rgba(128,128,128,.18); padding: 2px 6px; border-radius: 6px; font-size: 14px; }
  .sub { color: var(--sub); font-size: 13px; }
  a { color: var(--accent); }
</style>
</head>
<body>
  <h1>🎤 點歌系統操作手冊</h1>
  <p class="sub">在 LINE 聊天室直接傳文字指令，或打開 <a href="/karaoke">點歌網頁</a> 用按鈕操作，兩邊是同一份排隊，互相同步。</p>

  <h2>點歌</h2>
  <div class="card">
    <code>點歌 &lt;歌名或YouTube網址&gt;</code><br />
    例如：<code>點歌 小星星</code><br />
    <span class="sub">會自動搜尋 YouTube 並加入排隊，輪到就會自動播放。</span>
  </div>
  <div class="card">
    想點伴奏版（去掉人聲的版本），在歌名最後加一個 <code>0</code>：<br />
    <code>點歌 小星星0</code>
    <div class="sub">會自動搜尋「小星星 伴奏 instrumental」，找不到伴奏版的話會播原版。</div>
  </div>

  <h2>查看排隊</h2>
  <div class="card">
    <code>排隊</code>（或 <code>查詢</code> / <code>歌單</code>）<br />
    <span class="sub">會列出目前播放中的歌曲，跟排隊中的歌曲（含編號）。</span>
  </div>

  <h2>管理排隊</h2>
  <div class="card">
    <code>切歌</code> — 跳過目前這首，播下一首<br />
    <code>刪除 2</code> — 刪除排隊第 2 首（先傳「排隊」看編號）<br />
    <code>頂歌 2</code> — 把排隊第 2 首移到最前面，下一首就輪到它<br />
    <code>停止</code> — 停止播放，並清空整個排隊
  </div>

  <h2>原聲 / 伴奏切換</h2>
  <div class="card">
    <code>原聲</code> / <code>伴奏</code><br />
    <span class="sub">切換「目前正在播放」那首歌的版本。因為是重新搜尋另一個版本的影片來播，會從頭開始播，沒辦法接續原本播到的位置。</span>
  </div>

  <h2>熱門歌曲隨機播放</h2>
  <div class="card">
    <code>熱門 kpop</code> / <code>熱門 中文</code> / <code>熱門 英文</code><br />
    <span class="sub">開始從該分類隨機連續播放，一首播完自動接下一首（不會重複），一直播到你傳「暫停熱門」為止。網頁 /karaoke 頁面上也有對應的按鈕。排隊裡如果有人手動點歌，會先播完手動點的歌再繼續隨機播放。</span>
  </div>
  <div class="card">
    <code>暫停熱門</code>（或 <code>停止熱門</code>）<br />
    <span class="sub">立刻停止隨機播放（會直接切歌，不是播完當前這首才停）。</span>
  </div>

  <h2>網頁點歌頁面</h2>
  <div class="card">
    <a href="/karaoke">/karaoke</a><br />
    <span class="sub">現正播放、進度條、動態同步歌詞、點歌輸入框、排隊列表（可以頂歌/刪除）、熱門歌曲隨機播放按鈕都在這一頁，手機 LINE 內建瀏覽器打開就能用，每 1.5 秒自動更新一次。</span>
  </div>

  <h2>快速叫出這個頁面</h2>
  <div class="card">
    在 LINE 傳：<code>小樂小樂，我要點歌</code><br />
    <span class="sub">機器人會回傳點歌網頁連結 + 這份操作手冊連結。</span>
  </div>

  <h2>小提醒</h2>
  <div class="card sub">
    · 歌詞是從公開歌詞資料庫搜尋比對歌名找到的，不是每首歌都找得到同步歌詞，找不到會顯示「沒有找到歌詞」。<br />
    · 排隊、點歌、刪除這些操作，LINE 上任何人（跟網頁上任何看得到連結的人）都可以做，沒有身份限制。<br />
    · 音樂是從樹莓派本機的喇叭播放出來，不是傳到你手機播放。
  </div>
</body>
</html>
"""

app = Flask(__name__)
shield = Pi3Shield(debug=True)


def verify_signature(body: bytes, signature: str) -> bool:
    digest = hmac.new(CHANNEL_SECRET.encode('utf-8'), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode('utf-8')
    return hmac.compare_digest(expected, signature or '')


def line_reply(reply_token: str, text: str) -> None:
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
    }
    body = {'replyToken': reply_token, 'messages': [{'type': 'text', 'text': text}]}
    try:
        resp = requests.post(LINE_REPLY_URL, headers=headers, data=json.dumps(body), timeout=10)
        if resp.status_code >= 300:
            print(f"[line_reply] LINE API returned {resp.status_code}: {resp.text}")
    except requests.RequestException as exc:
        print(f"[line_reply] request failed: {exc}")


_display_name_cache: dict = {}


def get_display_name(user_id):
    if not user_id:
        return '匿名'
    if user_id in _display_name_cache:
        return _display_name_cache[user_id]
    name = '匿名'
    try:
        resp = requests.get(
            f'https://api.line.me/v2/bot/profile/{user_id}',
            headers={'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'},
            timeout=8,
        )
        if resp.status_code == 200:
            name = resp.json().get('displayName', '匿名')
    except requests.RequestException:
        pass
    _display_name_cache[user_id] = name
    return name


def _format_queue_text() -> str:
    status = karaoke.get_status()
    lines = []
    np = status['now_playing']
    if np:
        mode_label = '伴奏版' if np['mode'] == 'instrumental' else '原聲'
        lines.append(f"▶️ 現正播放：{np['title']}（{mode_label}，{np['requester']} 點）")
    else:
        lines.append('目前沒有播放中的歌曲')
    if status['queue']:
        lines.append('--- 排隊中 ---')
        for i, s in enumerate(status['queue'], 1):
            mode_label = '伴奏' if s['mode'] == 'instrumental' else '原聲'
            lines.append(f"{i}. {s['query']}（{mode_label}，{s['requester']} 點）")
    else:
        lines.append('目前沒有排隊歌曲')
    return '\n'.join(lines)


def handle_command(text: str, base_url: str = '', user_id: str = None) -> str:
    key = text.strip()
    lowered = key.lower()
    panel_url = f'{base_url}/panel' if base_url else ''
    karaoke_url = f'{base_url}/karaoke' if base_url else ''
    manual_url = f'{base_url}/manual' if base_url else ''

    if '小樂' in key and '點歌' in key:
        if not base_url:
            return '點歌頁面連結目前無法產生'
        return f"🎤 歡迎使用點歌系統！\n點歌頁面：{karaoke_url}\n操作手冊：{manual_url}\n\n快速上手：直接傳「點歌 歌名」就能加入排隊囉！"
    if lowered in ('面板', 'panel', '控制台'):
        return f"點這個連結打開圖形控制面板：\n{panel_url}" if panel_url else '面板連結目前無法產生'
    if lowered in ('help', 'menu', '?', '說明', '指令'):
        text_out = MENU_TEXT
        if panel_url:
            text_out += f"\n\n圖形控制面板：\n{panel_url}"
        if karaoke_url:
            text_out += f"\n點歌頁面：\n{karaoke_url}"
        return text_out
    if key == '1':
        shield.led_steady(bulb1=True)
        return '燈泡1 長亮'
    if key == '2':
        shield.led_steady(bulb2=True)
        return '燈泡2 長亮'
    if key == '3':
        shield.led_steady(bulb1=True, bulb2=True)
        return '燈泡1+2 一起長亮'
    if key == '4':
        shield.led_blink(bulb1=True)
        return '燈泡1 閃爍中'
    if key == '5':
        shield.led_blink(bulb2=True)
        return '燈泡2 閃爍中'
    if key == '6':
        shield.led_blink(bulb1=True, bulb2=True)
        return '燈泡1+2 一起閃爍中'
    if key == '0':
        shield.led_all_off()
        return '燈泡全部熄滅'
    if lowered in NOTE_KEYS:
        note = NOTE_KEYS[lowered]
        shield.play_note(note, duration=0.4)
        return f'播放音符 {note.upper()}'
    if lowered == 'p':
        threading.Thread(target=shield.play_song, args=(PAINTER_SONG,), daemon=True).start()
        return '開始播放《粉刷匠》🎵'
    if lowered == 'o':
        shield.relay_on()
        return '繼電器 開啟'
    if lowered == 'k':
        shield.relay_off()
        return '繼電器 關閉'

    # ---------- 點歌系統 ----------
    if key.startswith('點歌') or key.startswith('播放'):
        query = key[2:].strip()
        if not query:
            return '請在「點歌」後面加上歌名，例如：點歌 小星星（尾綴加0表示伴奏版，例如：點歌 小星星0）'
        mode = 'original'
        if not query.startswith(('http://', 'https://')) and query.endswith('0') and len(query) > 1:
            query = query[:-1].strip()
            mode = 'instrumental'
        requester = get_display_name(user_id)
        karaoke.add_song(query, requester, mode)
        mode_label = '伴奏版' if mode == 'instrumental' else '原聲'
        return f'🎤 已加入點歌佇列（{mode_label}）：{query}\n點歌人：{requester}'
    if lowered.startswith('play'):
        query = key[len('play'):].strip()
        if not query:
            return 'Usage: play <song name or YouTube URL>'
        requester = get_display_name(user_id)
        karaoke.add_song(query, requester, 'original')
        return f'🎤 已加入點歌佇列：{query}\n點歌人：{requester}'
    if lowered in ('排隊', '查詢', 'queue', '歌單'):
        return _format_queue_text()
    if lowered in ('切歌', 'skip'):
        karaoke.skip()
        return '⏭ 已切歌，播放下一首'
    if key.startswith('刪除'):
        num_str = key[2:].strip()
        status = karaoke.get_status()
        try:
            idx = int(num_str) - 1
            song = status['queue'][idx]
        except (ValueError, IndexError):
            return '請輸入正確的排隊編號，例如：刪除 2（先傳「排隊」查看編號）'
        karaoke.remove_song(song['id'])
        return f"🗑 已刪除：{song['query']}"
    if key.startswith('頂歌'):
        num_str = key[2:].strip()
        status = karaoke.get_status()
        try:
            idx = int(num_str) - 1
            song = status['queue'][idx]
        except (ValueError, IndexError):
            return '請輸入正確的排隊編號，例如：頂歌 2（先傳「排隊」查看編號）'
        karaoke.move_to_front(song['id'])
        return f"⬆️ 已將「{song['query']}」移到最前面"
    if lowered in ('原聲', '原声'):
        ok = karaoke.switch_mode('original')
        return '🎤 切換成原聲版（重新播放）' if ok else '目前沒有播放中的歌曲'
    if lowered == '伴奏':
        ok = karaoke.switch_mode('instrumental')
        return '🎹 切換成伴奏版（重新播放）' if ok else '目前沒有播放中的歌曲'
    if lowered in ('停止', '停止音樂', 'stop'):
        karaoke.stop_all()
        return '⏹ 已停止播放並清空點歌佇列'

    # ---------- 熱門歌曲隨機連續播放 ----------
    if key.startswith('熱門'):
        arg = key[2:].strip().lower()
        category_map = {
            'kpop': 'kpop', 'k-pop': 'kpop', '韓': 'kpop', '韓文': 'kpop', '韓語': 'kpop',
            '中文': 'cpop', '中文流行': 'cpop', '華語': 'cpop', '國語': 'cpop', 'cpop': 'cpop',
            '英文': 'epop', '英文流行': 'epop', '英語': 'epop', 'epop': 'epop',
        }
        category = category_map.get(arg)
        if not category:
            return '請指定分類，例如：熱門 kpop / 熱門 中文 / 熱門 英文'
        karaoke.start_radio(category)
        label = karaoke.CATEGORY_LABELS[category]
        return f'🔀 開始隨機播放熱門歌曲（{label}），播完會自動接下一首，傳「暫停熱門」可以停止'
    if lowered in ('暫停熱門', '停止熱門', 'stop radio'):
        karaoke.stop_radio()
        return '⏸ 已暫停熱門播放'
    return f'不認識的指令: {text}\n輸入 help 查看指令列表'


@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data()
    if not verify_signature(body, signature):
        abort(400)

    base_url = f"https://{request.host}"
    panel_url = f"{base_url}/panel"
    payload = json.loads(body.decode('utf-8'))
    for event in payload.get('events', []):
        reply_token = event.get('replyToken')
        event_type = event.get('type')
        user_id = event.get('source', {}).get('userId')

        if event_type == 'follow':
            if reply_token:
                line_reply(reply_token, f"歡迎使用 Pi3 Shield！\n點這個連結打開圖形控制面板：\n{panel_url}\n\n也可以直接傳文字指令，輸入 help 查看列表。")
            continue

        if event_type != 'message':
            continue
        message = event.get('message', {})
        if message.get('type') != 'text':
            continue
        reply_text = handle_command(message.get('text', ''), base_url=base_url, user_id=user_id)
        if reply_token:
            line_reply(reply_token, reply_text)

    return 'OK'


@app.route('/', methods=['GET'])
def index():
    return 'Pi3 Shield LINE Bot is running.'


@app.route('/panel', methods=['GET'])
def panel():
    return PANEL_HTML


@app.route('/karaoke', methods=['GET'])
def karaoke_page():
    return KARAOKE_HTML


@app.route('/manual', methods=['GET'])
def manual_page():
    return MANUAL_HTML


@app.route('/api/karaoke/status', methods=['GET'])
def api_karaoke_status():
    status = karaoke.get_status()
    lyrics = None
    if status['now_playing']:
        np = status['now_playing']
        # 先用使用者輸入的乾淨歌名搜歌詞，YouTube 標題常常太雜亂（含頻道名稱等），當備援用
        lyrics = karaoke.fetch_lyrics(np['query'], np['title'])
    status['lyrics'] = lyrics
    return jsonify(status)


@app.route('/api/karaoke/add', methods=['POST'])
def api_karaoke_add():
    data = request.get_json(force=True, silent=True) or {}
    query = (data.get('query') or '').strip()
    if not query:
        return jsonify({'status': 'error', 'message': 'empty query'}), 400
    requester = data.get('requester') or '網頁點歌'
    mode = data.get('mode') if data.get('mode') in ('original', 'instrumental') else 'original'
    song = karaoke.add_song(query, requester, mode)
    return jsonify({'status': 'ok', 'id': song.id})


@app.route('/api/karaoke/remove', methods=['POST'])
def api_karaoke_remove():
    data = request.get_json(force=True, silent=True) or {}
    song_id = data.get('id')
    if not song_id:
        return jsonify({'status': 'error', 'message': 'missing id'}), 400
    karaoke.remove_song(song_id)
    return jsonify({'status': 'ok'})


@app.route('/api/karaoke/priority', methods=['POST'])
def api_karaoke_priority():
    data = request.get_json(force=True, silent=True) or {}
    song_id = data.get('id')
    if not song_id:
        return jsonify({'status': 'error', 'message': 'missing id'}), 400
    karaoke.move_to_front(song_id)
    return jsonify({'status': 'ok'})


@app.route('/api/karaoke/skip', methods=['POST'])
def api_karaoke_skip():
    karaoke.skip()
    return jsonify({'status': 'ok'})


@app.route('/api/karaoke/mode', methods=['POST'])
def api_karaoke_mode():
    data = request.get_json(force=True, silent=True) or {}
    mode = data.get('mode')
    if mode not in ('original', 'instrumental'):
        return jsonify({'status': 'error', 'message': 'mode must be original or instrumental'}), 400
    ok = karaoke.switch_mode(mode)
    return jsonify({'status': 'ok' if ok else 'error'})


@app.route('/api/karaoke/radio', methods=['POST'])
def api_karaoke_radio():
    data = request.get_json(force=True, silent=True) or {}
    category = data.get('category')
    if category not in karaoke.POPULAR_SONGS:
        return jsonify({'status': 'error', 'message': f'category must be one of {list(karaoke.POPULAR_SONGS)}'}), 400
    karaoke.start_radio(category)
    return jsonify({'status': 'ok', 'category': category})


@app.route('/api/karaoke/radio/stop', methods=['POST'])
def api_karaoke_radio_stop():
    karaoke.stop_radio()
    return jsonify({'status': 'ok'})


@app.route('/api/led', methods=['GET'])
def api_led():
    action = request.args.get('action', '')
    actions = {
        'steady1': lambda: shield.led_steady(bulb1=True),
        'steady2': lambda: shield.led_steady(bulb2=True),
        'steady_both': lambda: shield.led_steady(bulb1=True, bulb2=True),
        'blink1': lambda: shield.led_blink(bulb1=True),
        'blink2': lambda: shield.led_blink(bulb2=True),
        'blink_both': lambda: shield.led_blink(bulb1=True, bulb2=True),
        'off': shield.led_all_off,
    }
    fn = actions.get(action)
    if fn is None:
        return jsonify({'status': 'error', 'message': f'unknown action: {action}'}), 400
    fn()
    return jsonify({'status': 'ok', 'action': action})


@app.route('/api/note', methods=['GET'])
def api_note():
    name = request.args.get('name', '')
    try:
        shield.play_note(name, duration=0.4)
    except ValueError as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 400
    return jsonify({'status': 'ok', 'note': name})


@app.route('/api/song', methods=['GET'])
def api_song():
    threading.Thread(target=shield.play_song, args=(PAINTER_SONG,), daemon=True).start()
    return jsonify({'status': 'ok', 'message': 'playing painter song'})


@app.route('/api/relay', methods=['GET'])
def api_relay():
    action = request.args.get('action', '')
    if action == 'on':
        shield.relay_on()
    elif action == 'off':
        shield.relay_off()
    else:
        return jsonify({'status': 'error', 'message': f'unknown action: {action}'}), 400
    return jsonify({'status': 'ok', 'relay': action})


def main():
    karaoke.start()
    try:
        app.run(host='0.0.0.0', port=8000, threaded=True)
    finally:
        karaoke.stop_all()
        shield.cleanup()


if __name__ == '__main__':
    main()
