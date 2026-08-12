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
import time

import requests
from flask import Flask, abort, jsonify, request

import karaoke
import song_stats
import weather
import ir_remote
import nlu
import stt
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
    "小樂點歌台（詳見操作手冊）：\n"
    "  點歌 <歌名>       = 加入排隊（尾綴0=伴奏版，例如「點歌 小星星0」）\n"
    "  @任何稱呼 <歌名>   = 跟點歌一樣，更口語（例如「@小樂 稻香」）\n"
    "  推薦 <歌手>        = 不知道歌名時，推薦該歌手前5首熱門歌，回數字直接點\n"
    "  排隊              = 查看目前播放/排隊列表\n"
    "  切歌 / 刪除 <編號> / 頂歌 <編號>\n"
    "  暫停 / 繼續        = 暫停或接著播（從原本位置繼續，不會重頭）\n"
    "  原聲 / 伴奏        = 切換目前播放的版本\n"
    "  停止              = 停止播放並清空排隊\n"
    "  熱門 kpop/中文/英文 = 隨機連續播放熱門歌曲，直到「暫停熱門」\n"
    "  常點 / 我的常點     = 列出你最常點的歌，回數字直接點\n"\
    "  熱門排行           = 全場最常被點的歌\n"\
    "  大螢幕 = 傳送接電視/顯示器用的大字歌詞頁面連結\n"
    "  小樂小樂，我要點歌 = 傳送點歌頁面連結+操作手冊\n"
    "  以上都比對不到的話，也可以直接用口語講（例如「我想聽周杰倫的稻香」\n"
    "  「可以跳過這首嗎」），機器人會試著聽懂（需要本機 AI 服務有開）\n"
    "  直接傳「語音訊息」也可以點歌，不用打字，機器人會轉成文字再照上面的規則處理\n"\
    "\n"\
    "生活功能：\n"\
    "  天氣 / 氣溫        = 查目前天氣（新北市三重）\n"\
    "  開風扇 / 關風扇     = 紅外線遙控風扇\n"
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
<title>小樂點歌台</title>
<style>
  /* ================================================================
     小樂點歌台 — Y2K 霓虹賽博 × 輕潮簡約
     視覺原則：
       1. 顏色靠「透」不靠「亮」——低飽和光暈穿過毛玻璃，不用實心彩色塊
       2. 不用邊框切割版面——用發光和模糊界定範圍
       3. 只做一套深色。這是 KTV 系統，使用場景就是昏暗的房間 + 音樂。
     背景由四層構成：極光 → 模糊聲波 → 互動星空 → 顆粒。
     ================================================================ */
  :root {
    color-scheme: dark;

    --ink:   #07080F;   /* 底：深炭灰帶藍，不是純黑 */
    --mist:  #7FA8D9;   /* 霧藍 */
    --taro:  #A88BE0;   /* 香芋紫 */
    --mint:  #6FE3C4;   /* 淺薄荷 */
    --blush: #E68FC8;   /* 粉紫 */
    --sun:   #F0C98A;   /* 暖砂，只給 VU 峰值 */

    --text:  #E8EAF4;
    --sub:   #949AB5;
    --dim:   #626883;

    --glass:    rgba(255,255,255,.042);
    --glass-hi: rgba(255,255,255,.10);
    --hairline: rgba(255,255,255,.07);

    --r-lg: 30px;
    --r-md: 20px;
    --r-sm: 14px;
  }

  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html { scrollbar-width: none; }
  html::-webkit-scrollbar { display: none; }

  body {
    margin: 0; min-height: 100vh; position: relative; overflow-x: hidden;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI",
                 "PingFang TC", "Noto Sans TC", "Microsoft JhengHei", sans-serif;
    color: var(--text); background: var(--ink);
    padding: 26px 16px 72px;
  }

  /* ---------- 背景層 ---------- */
  .aurora { position: fixed; border-radius: 50%; pointer-events: none; z-index: 0;
            filter: blur(100px); will-change: transform; }
  .au-1 { width: 68vw; height: 68vw; max-width: 800px; max-height: 800px;
          top: -22vw; right: -14vw; opacity: .48;
          background: radial-gradient(circle, var(--taro) 0%, transparent 66%);
          animation: au1 26s ease-in-out infinite alternate; }
  .au-2 { width: 60vw; height: 60vw; max-width: 720px; max-height: 720px;
          bottom: -18vw; left: -16vw; opacity: .36;
          background: radial-gradient(circle, var(--mist) 0%, transparent 66%);
          animation: au2 33s ease-in-out infinite alternate; }
  .au-3 { width: 42vw; height: 42vw; max-width: 520px; max-height: 520px;
          top: 44%; left: 44%; opacity: .22;
          background: radial-gradient(circle, var(--mint) 0%, transparent 68%);
          animation: au3 40s ease-in-out infinite alternate; }
  @keyframes au1 { to { transform: translate3d(-8vw, 7vh, 0) scale(1.15); } }
  @keyframes au2 { to { transform: translate3d(7vw, -6vh, 0) scale(1.10); } }
  @keyframes au3 { to { transform: translate3d(-10vw, -8vh, 0) scale(1.22); } }

  #wave  { position: fixed; left: 0; bottom: 0; width: 100%; height: 46vh;
           z-index: 0; pointer-events: none; filter: blur(16px); opacity: .5; }
  #stars { position: fixed; inset: 0; width: 100%; height: 100%;
           z-index: 1; pointer-events: none; }

  .grain { position: fixed; inset: 0; pointer-events: none; z-index: 2; opacity: .05;
    mix-blend-mode: overlay;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='4'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)'/%3E%3C/svg%3E"); }

  .wrap { position: relative; z-index: 4; max-width: 480px; margin: 0 auto; }
  .layout { display: grid; grid-template-columns: 1fr; gap: 18px; align-items: start; }
  .layout, .col, .panel { min-width: 0; }

  @media (min-width: 900px) {
    body { padding: 38px 30px 72px; }
    .wrap { max-width: 1220px; }
    .layout { grid-template-columns: minmax(0, 1.52fr) minmax(0, 1fr); gap: 26px; }
    .col { display: grid; gap: 22px; align-content: start; }
    .col-left { position: sticky; top: 28px; }
  }
  @media (min-width: 1320px) {
    body { padding: 42px 40px 72px; }
    .wrap { max-width: 1400px; }
    .layout { grid-template-columns: minmax(0, 1.62fr) minmax(0, 1fr); gap: 32px; }
  }
  @media (min-width: 1600px) { body { padding: 46px 52px 76px; } .wrap { max-width: 1580px; } }
  @media (min-width: 1900px) { .wrap { max-width: 1760px; } }

  /* ---------- 品牌 ---------- */
  .brand { margin-bottom: 26px; text-align: center; }
  .on-air {
    display: inline-flex; align-items: center; gap: 8px;
    font-size: 10px; font-weight: 800; letter-spacing: .28em; text-transform: uppercase;
    color: var(--dim); padding: 6px 14px; border-radius: 999px;
    background: var(--glass); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
    transition: color .35s, box-shadow .35s;
  }
  .on-air i { width: 6px; height: 6px; border-radius: 50%; background: var(--dim);
              transition: background .35s, box-shadow .35s; }
  .on-air.live { color: var(--mint); box-shadow: 0 0 26px rgba(111,227,196,.16); }
  .on-air.live i { background: var(--mint); box-shadow: 0 0 12px var(--mint);
                   animation: breathe 2.4s ease-in-out infinite; }
  @keyframes breathe { 50% { opacity: .35; } }

  .wordmark {
    font-size: 36px; font-weight: 900; letter-spacing: .04em; margin: 12px 0 0;
    background: linear-gradient(105deg, var(--mist) 0%, var(--taro) 38%, var(--blush) 66%, var(--mint) 100%);
    -webkit-background-clip: text; background-clip: text; color: transparent;
    filter: drop-shadow(0 0 22px rgba(168,139,224,.4));
  }
  .brand-sub { font-size: 9.5px; letter-spacing: .42em; text-transform: uppercase;
               color: var(--dim); margin-top: 9px; }
  @media (min-width: 900px) {
    .brand { text-align: left; margin-bottom: 30px; }
    .wordmark { font-size: 50px; }
  }

  /* ---------- 面板 ---------- */
  /* 面板刻意「不」用 backdrop-filter：
     1px 的星點被 20px 模糊一抹就消失，天蠍座整個看不到。
     改成只留一層很薄的暗色紗 + 髮絲描邊，背景星空直接透過來。
     可讀性改用 text-shadow 撐住，不靠底色遮擋。 */
  .panel {
    position: relative; border-radius: var(--r-lg); padding: 24px;
    background: rgba(8,10,18,.24);
    box-shadow: 0 14px 44px rgba(0,0,0,.22), inset 0 1px 0 rgba(255,255,255,.07);
    text-shadow: 0 1px 3px rgba(3,4,10,.88);
    margin-bottom: 18px; overflow: hidden;
  }
  .col .panel { margin-bottom: 0; }
  .panel::before {
    content: ''; position: absolute; inset: 0; pointer-events: none; border-radius: inherit;
    background: radial-gradient(380px circle at var(--mx, 50%) var(--my, 0%),
                rgba(255,255,255,.08), transparent 62%);
    opacity: 0; transition: opacity .4s;
  }
  .panel:hover::before { opacity: 1; }
  .panel::after {
    content: ''; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
    padding: 1px;
    background: linear-gradient(150deg, rgba(255,255,255,.12), rgba(255,255,255,.02) 40%, transparent 70%);
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    -webkit-mask-composite: xor; mask-composite: exclude;
  }
  .panel > * { position: relative; z-index: 1; }

  .label {
    font-size: 10px; color: var(--sub); font-weight: 800; margin-bottom: 16px;
    text-transform: uppercase; letter-spacing: .24em;
    display: flex; align-items: center; gap: 8px;
  }
  .tally { margin-left: auto; font-size: 10px; font-weight: 800; letter-spacing: 0;
           color: var(--taro); background: rgba(168,139,224,.13);
           padding: 3px 10px; border-radius: 999px; }
  .muted { color: var(--sub); font-weight: 400; }

  /* ================= 3D 唱盤機 ================= */
  .deck-stage {
    position: relative; min-height: 280px; margin: -6px -10px 0;
    display: flex; align-items: center; justify-content: center;
    perspective: 1200px; perspective-origin: 50% 34%;
  }
  @media (min-width: 900px) { .deck-stage { min-height: 350px; margin: 0 0 4px; } }

  /* --- 光圈：兩圈反向旋轉的霓虹環 + 一層柔光 --- */
  .halo { position: absolute; width: 268px; height: 268px; pointer-events: none;
          transform: scale(calc(1 + var(--beat, 0) * .055)); }
  @media (min-width: 900px) { .halo { width: 340px; height: 340px; } }
  .halo .ring { position: absolute; inset: 0; border-radius: 50%;
    -webkit-mask: radial-gradient(circle, transparent 0 66%, #000 67.5%, #000 70%, transparent 71.5%);
    mask: radial-gradient(circle, transparent 0 66%, #000 67.5%, #000 70%, transparent 71.5%);
    animation: ring-a 16s linear infinite; }
  .halo .ring.r1 { background: conic-gradient(from 0deg,
      transparent 0deg, var(--taro) 46deg, var(--blush) 96deg, transparent 168deg,
      transparent 200deg, var(--mist) 268deg, transparent 330deg); opacity: .85; }
  .halo .ring.r2 { inset: -16px; animation: ring-b 26s linear infinite; opacity: .45;
    background: conic-gradient(from 140deg,
      transparent 0deg, var(--mint) 60deg, transparent 130deg,
      transparent 250deg, var(--taro) 310deg, transparent 360deg); }
  .halo .bloom { position: absolute; inset: 8%; border-radius: 50%;
    background: radial-gradient(circle, rgba(168,139,224,.32) 0%, rgba(127,168,217,.11) 46%, transparent 70%);
    filter: blur(18px); opacity: calc(.42 + var(--beat, 0) * .58); }
  /* 震波：每個重拍從光圈往外擴一圈 */
  .halo .shock { position: absolute; inset: 0; border-radius: 50%;
    box-shadow: 0 0 0 1.5px rgba(232,143,200,.55), 0 0 22px rgba(232,143,200,.28);
    transform: scale(calc(1 + var(--pulse, 1) * .40));
    opacity: calc((1 - var(--pulse, 1)) * .6); }
  .deck-stage.live .halo .ring.r1 { animation-duration: 9s; }
  @keyframes ring-a { to { transform: rotate(360deg); } }
  @keyframes ring-b { to { transform: rotate(-360deg); } }

  /* --- 盤體 --- */
  .deck {
    position: relative; width: 244px; height: 176px; flex-shrink: 0;
    transform-style: preserve-3d;
    transform: rotateX(57deg) rotateZ(calc(-19deg + var(--rz, 0deg))) rotateY(var(--ry, 0deg));
  }
  @media (min-width: 900px) { .deck { width: 306px; height: 220px; } }

  /* 厚度：一層層 box-shadow 疊出板子的側面 */
  .deck-base {
    position: absolute; inset: 0; border-radius: 26px;
    background: linear-gradient(152deg, #262b3e 0%, #1a1f2e 44%, #0f1320 100%);
    box-shadow:
      0 2px 0 #1d2130, 0 4px 0 #1b1f2d, 0 6px 0 #191d2a, 0 8px 0 #171b27,
      0 10px 0 #151924, 0 12px 0 #131721, 0 14px 0 #11151e, 0 16px 0 #0f131b,
      0 18px 0 #0d1118, 0 20px 0 #0b0f15,
      0 46px 70px rgba(0,0,0,.68),
      inset 0 1px 0 rgba(255,255,255,.13);
  }
  /* 盤面刻字 */
  .deck-etch {
    position: absolute; left: 7%; bottom: 9%; pointer-events: none;
    font-size: 11px; font-weight: 900; letter-spacing: .12em; line-height: 1.5;
    color: rgba(255,255,255,.20);
    text-shadow: 0 1px 0 rgba(255,255,255,.07), 0 -1px 0 rgba(0,0,0,.55);
  }
  .deck-etch small { display: block; font-size: 7px; font-weight: 700;
                     letter-spacing: .34em; color: rgba(255,255,255,.13); margin-top: 3px; }
  @media (min-width: 900px) { .deck-etch { font-size: 13px; } .deck-etch small { font-size: 8px; } }

  .platter {
    position: absolute; left: 4%; top: 50%; width: 148px; height: 148px;
    margin-top: -74px; border-radius: 50%;
    background: radial-gradient(circle, #20263a 0%, #0e111d 78%);
    box-shadow: inset 0 0 0 1px rgba(255,255,255,.06), inset 0 0 34px rgba(0,0,0,.85);
  }
  @media (min-width: 900px) { .platter { width: 186px; height: 186px; margin-top: -93px; } }
  .record {
    position: absolute; inset: 5%; border-radius: 50%;
    background:
      repeating-radial-gradient(circle, rgba(255,255,255,.06) 0 1px, transparent 1px 5px),
      conic-gradient(from 0deg,
        #181c2b 0deg, #303650 32deg, #161a28 76deg, #2a3048 130deg,
        #151927 188deg, #343a56 242deg, #171b2a 298deg, #181c2b 360deg);
    box-shadow: inset 0 0 42px rgba(0,0,0,.88), 0 0 40px rgba(168,139,224,.22);
  }
  .record.spinning { animation: spin 2.4s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .rec-label {
    position: absolute; left: 50%; top: 50%; width: 33%; height: 33%;
    margin: -16.5% 0 0 -16.5%; border-radius: 50%;
    background: conic-gradient(from 210deg, var(--mint), var(--mist) 22%, var(--taro) 52%, var(--blush) 78%, var(--mint));
    box-shadow: 0 0 26px rgba(232,143,200,.5), inset 0 -2px 6px rgba(0,0,0,.35);
    display: flex; align-items: center; justify-content: center;
  }
  .rec-label::after { content: ''; width: 14%; height: 14%; border-radius: 50%;
                      background: #07080F; box-shadow: inset 0 0 4px rgba(0,0,0,.9); }

  /* 唱針：待機停在外側，播放時擺進盤面 */
  .tonearm {
    position: absolute; right: 6%; top: 12%; width: 42%; height: 8px;
    transform-origin: calc(100% - 10px) 50%;
    transform: rotate(30deg);
    transition: transform .95s cubic-bezier(.4,.05,.2,1);
  }
  .tonearm.on { transform: rotate(62deg); }
  .tonearm .arm { position: absolute; left: 15px; right: 13px; top: 3px; height: 3px;
    border-radius: 2px; background: linear-gradient(90deg, #7a8099, #a3aac6);
    box-shadow: 0 1px 3px rgba(0,0,0,.65); }
  .tonearm .pivot { position: absolute; right: 0; top: 50%; width: 20px; height: 20px;
    margin-top: -10px; border-radius: 50%;
    background: radial-gradient(circle at 34% 28%, #4a5169, #1b1f2e);
    box-shadow: 0 3px 9px rgba(0,0,0,.65), inset 0 1px 0 rgba(255,255,255,.18); }
  .tonearm .head { position: absolute; left: 0; top: 50%; width: 16px; height: 9px;
    margin-top: -4.5px; border-radius: 3px;
    background: linear-gradient(135deg, #a3aac6, #565d78);
    box-shadow: 0 2px 5px rgba(0,0,0,.6); }

  .deck-leds { position: absolute; right: 8%; bottom: 12%; display: flex; gap: 9px; }
  .deck-leds i { width: 8px; height: 8px; border-radius: 50%;
                 background: rgba(255,255,255,.09);
                 box-shadow: inset 0 1px 2px rgba(0,0,0,.6); transition: all .4s; }
  .deck-leds i.on:nth-child(1) { background: var(--mint); box-shadow: 0 0 12px var(--mint); }
  .deck-leds i.on:nth-child(2) { background: var(--blush); box-shadow: 0 0 12px var(--blush); }

  /* ---------- 現正播放 ---------- */
  .np { margin-top: 14px; text-align: center; }
  @media (min-width: 900px) { .np { text-align: left; } }
  .np-title {
    font-size: 21px; font-weight: 800; line-height: 1.3; letter-spacing: -.01em;
    overflow: hidden; text-overflow: ellipsis; display: -webkit-box;
    -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow-wrap: anywhere; word-break: break-word;
  }
  @media (min-width: 900px) { .np-title { font-size: 27px; } }
  .np-sub { font-size: 12px; color: var(--sub); margin-top: 10px;
            display: flex; align-items: center; gap: 8px; justify-content: center; flex-wrap: wrap; }
  @media (min-width: 900px) { .np-sub { justify-content: flex-start; } }
  .chip { padding: 4px 12px; border-radius: 999px; font-size: 10.5px; font-weight: 800;
          letter-spacing: .06em; color: var(--taro); background: rgba(168,139,224,.14); }
  .chip.alt { color: var(--mint); background: rgba(111,227,196,.13); }

  .bar { height: 4px; border-radius: 99px; margin-top: 20px;
         background: rgba(255,255,255,.07); overflow: hidden; }
  .bar > i { display: block; height: 100%; width: 0%; border-radius: 99px;
    background: linear-gradient(90deg, var(--mist), var(--taro) 52%, var(--blush));
    box-shadow: 0 0 14px rgba(168,139,224,.6); transition: width .3s linear; }
  .clock { font-size: 10.5px; color: var(--dim); margin-top: 10px;
           font-variant-numeric: tabular-nums; letter-spacing: .08em;
           display: flex; justify-content: space-between; }

  /* ---------- 按鈕：一律毛玻璃 ---------- */
  .row { display: flex; gap: 10px; margin-top: 18px; }
  .btn {
    flex: 1; padding: 14px 8px; border-radius: var(--r-md); border: none;
    font-size: 13px; font-weight: 700; letter-spacing: .02em; color: var(--text);
    background: rgba(255,255,255,.075); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
    box-shadow: inset 0 0 0 1px rgba(255,255,255,.10);
    text-shadow: none;
    cursor: pointer; transition: transform .14s, box-shadow .3s, background .3s, color .3s;
  }
  .btn:hover { background: var(--glass-hi);
               box-shadow: inset 0 0 0 1px rgba(255,255,255,.13), 0 0 26px rgba(168,139,224,.22); }
  .btn:active { transform: scale(.965); }
  .btn:focus-visible { outline: 2px solid var(--mint); outline-offset: 3px; }
  .btn.on { color: #fff;
    background: linear-gradient(140deg, rgba(168,139,224,.30), rgba(127,168,217,.16));
    box-shadow: inset 0 0 0 1px rgba(168,139,224,.36), 0 0 30px rgba(168,139,224,.26); }
  .btn.on-mint { color: #fff;
    background: linear-gradient(140deg, rgba(111,227,196,.26), rgba(127,168,217,.14));
    box-shadow: inset 0 0 0 1px rgba(111,227,196,.34), 0 0 30px rgba(111,227,196,.22); }

  /* ---------- 歌詞：半透浮層 ---------- */
  .lyrics-float {
    position: relative; padding: 26px 20px; border-radius: var(--r-lg);
    background: radial-gradient(120% 100% at 50% 0%, rgba(255,255,255,.04), transparent 72%);
    text-shadow: 0 1px 4px rgba(3,4,10,.9);
    min-height: 168px; display: flex; flex-direction: column;
    justify-content: center; gap: 15px; text-align: center; margin-bottom: 18px;
  }
  .col .lyrics-float { margin-bottom: 0; }
  @media (min-width: 900px) { .lyrics-float { min-height: 206px; } }
  .ly { font-size: 14px; color: var(--dim); transition: all .45s cubic-bezier(.2,.7,.3,1);
        overflow-wrap: anywhere; }
  .ly.near { color: var(--sub); }
  .ly.cur { font-size: 23px; font-weight: 800; color: #fff; letter-spacing: -.01em;
    text-shadow: 0 0 18px rgba(232,143,200,.55), 0 0 44px rgba(168,139,224,.4); }
  @media (min-width: 900px) { .ly.cur { font-size: 30px; } }

  /* ---------- 音場 ---------- */
  .vu { display: flex; align-items: flex-end; gap: 3px; height: 46px; margin-bottom: 20px; }
  .vu span { flex: 1; border-radius: 99px; height: 8%; opacity: .26;
    background: linear-gradient(to top, var(--mist), var(--taro) 46%, var(--blush) 78%, var(--sun));
    transition: height .16s ease, opacity .4s; }
  .vu.on span { opacity: .95; }

  .vol-row { display: flex; align-items: center; gap: 14px; }
  .vol-row .ic { font-size: 13px; opacity: .5; flex-shrink: 0; }
  .vol-num { font-size: 11.5px; font-weight: 800; color: var(--mint); min-width: 42px;
             text-align: right; font-variant-numeric: tabular-nums; flex-shrink: 0;
             letter-spacing: .05em; }
  input[type=range].vol {
    -webkit-appearance: none; appearance: none; flex: 1; min-width: 0;
    height: 4px; border-radius: 99px; outline: none; cursor: pointer;
    background: rgba(255,255,255,.09);
  }
  input[type=range].vol::-webkit-slider-thumb {
    -webkit-appearance: none; appearance: none; width: 18px; height: 18px; border-radius: 50%;
    background: rgba(255,255,255,.92); border: none;
    box-shadow: 0 0 14px rgba(111,227,196,.7), 0 0 0 4px rgba(111,227,196,.14);
  }
  input[type=range].vol::-moz-range-thumb {
    width: 18px; height: 18px; border-radius: 50%; border: none; background: rgba(255,255,255,.92);
    box-shadow: 0 0 14px rgba(111,227,196,.7), 0 0 0 4px rgba(111,227,196,.14);
  }

  /* ---------- 點歌 ---------- */
  .field {
    display: flex; align-items: center; gap: 12px; border-radius: var(--r-md);
    background: rgba(255,255,255,.07); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
    padding: 3px 8px 3px 16px; box-shadow: inset 0 0 0 1px rgba(255,255,255,.10);
    transition: box-shadow .3s, background .3s;
  }
  .field:focus-within {
    background: rgba(255,255,255,.07);
    box-shadow: inset 0 0 0 1px rgba(111,227,196,.4), 0 0 26px rgba(111,227,196,.16);
  }
  .field .ic { color: var(--dim); font-size: 13px; }
  .field input { flex: 1; min-width: 0; border: none; background: transparent; color: var(--text);
                 font-size: 15px; padding: 14px 4px; outline: none; }
  .field input::placeholder { color: var(--dim); }
  .hint { font-size: 11px; color: var(--dim); margin-top: 10px; min-height: 16px; letter-spacing: .02em; }

  .seg { display: flex; gap: 6px; margin-top: 14px; }
  .seg .btn { padding: 12px 8px; font-size: 12.5px; border-radius: var(--r-sm); }

  .cta {
    margin-top: 14px; width: 100%; padding: 15px; border-radius: var(--r-md); border: none;
    font-size: 14.5px; font-weight: 800; letter-spacing: .04em; color: #fff; cursor: pointer;
    background: linear-gradient(140deg, rgba(168,139,224,.32), rgba(232,143,200,.20) 55%, rgba(111,227,196,.16));
    backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
    box-shadow: inset 0 0 0 1px rgba(255,255,255,.16), 0 0 32px rgba(168,139,224,.24);
    text-shadow: none; transition: transform .14s, box-shadow .3s;
  }
  .cta:hover { box-shadow: inset 0 0 0 1px rgba(255,255,255,.2), 0 0 44px rgba(168,139,224,.4); }
  .cta:active { transform: scale(.975); }

  /* ---------- 頻道 ---------- */
  .radio-now { font-size: 12px; color: var(--sub); margin-bottom: 14px; min-height: 18px; font-weight: 600; }
  .radio-row { display: flex; gap: 10px; }
  .rbtn {
    flex: 1; padding: 16px 6px; border-radius: var(--r-md); border: none; cursor: pointer;
    font-size: 12px; font-weight: 700; color: var(--text);
    background: rgba(255,255,255,.075); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
    box-shadow: inset 0 0 0 1px rgba(255,255,255,.10);
    text-shadow: none;
    display: flex; flex-direction: column; align-items: center; gap: 7px;
    transition: transform .14s, box-shadow .3s, background .3s;
  }
  .rbtn .em { font-size: 18px; filter: saturate(.85); }
  .rbtn:hover { background: var(--glass-hi);
                box-shadow: inset 0 0 0 1px rgba(255,255,255,.13), 0 0 24px rgba(127,168,217,.2); }
  .rbtn:active { transform: scale(.965); }
  .rbtn.kpop.on { background: linear-gradient(140deg, rgba(168,139,224,.30), rgba(232,143,200,.16));
                  box-shadow: inset 0 0 0 1px rgba(168,139,224,.4), 0 0 30px rgba(168,139,224,.3); }
  .rbtn.cpop.on { background: linear-gradient(140deg, rgba(232,143,200,.28), rgba(240,201,138,.15));
                  box-shadow: inset 0 0 0 1px rgba(232,143,200,.4), 0 0 30px rgba(232,143,200,.28); }
  .rbtn.epop.on { background: linear-gradient(140deg, rgba(111,227,196,.26), rgba(127,168,217,.16));
                  box-shadow: inset 0 0 0 1px rgba(111,227,196,.4), 0 0 30px rgba(111,227,196,.26); }

  /* ---------- 清單 ---------- */
  .empty { color: var(--dim); font-size: 13px; text-align: center; padding: 20px 0; }
  .item { display: flex; align-items: center; gap: 13px; padding: 13px 10px;
          border-radius: var(--r-sm); margin: 0 -10px; transition: background .25s; }
  .item + .item { box-shadow: inset 0 1px 0 rgba(255,255,255,.07); }
  .item:hover { background: rgba(255,255,255,.04); }
  .idx { width: 30px; height: 30px; border-radius: 11px; flex-shrink: 0;
         font-size: 11.5px; font-weight: 800; color: var(--taro);
         background: rgba(168,139,224,.14);
         display: flex; align-items: center; justify-content: center; }
  .idx.play { color: var(--mint); background: rgba(111,227,196,.13); }
  .it-info { flex: 1; min-width: 0; }
  .it-title { font-size: 13.5px; font-weight: 600; overflow-wrap: anywhere; word-break: break-word; }
  .it-sub { font-size: 11px; color: var(--dim); margin-top: 4px; overflow-wrap: anywhere; }
  .mini { width: 33px; height: 33px; border-radius: 11px; flex-shrink: 0; border: none; cursor: pointer;
          font-size: 12px; font-weight: 700; color: var(--sub);
          background: rgba(255,255,255,.07); backdrop-filter: blur(12px);
          box-shadow: inset 0 0 0 1px rgba(255,255,255,.10);
          text-shadow: none; transition: all .2s; }
  .mini:hover { color: var(--text); background: rgba(255,255,255,.09); }
  .mini:active { transform: scale(.9); }
  .mini.del:hover { color: var(--blush); box-shadow: inset 0 0 0 1px rgba(232,143,200,.32); }
  .mini.again { color: var(--mint); }
  .hist { cursor: pointer; }

  @media (prefers-reduced-motion: reduce) {
    .aurora, .record.spinning, .on-air.live i, .halo .ring { animation: none; }
    .vu span, .ly, .tonearm { transition: none; }
    #wave { display: none; }
  }
</style>
</head>
<body>
  <div class="aurora au-1"></div>
  <div class="aurora au-2"></div>
  <div class="aurora au-3"></div>
  <canvas id="wave"></canvas>
  <canvas id="stars"></canvas>
  <div class="grain"></div>

  <div class="wrap">
  <div class="brand">
    <div class="on-air" id="on-air"><i></i><span id="on-air-text">Standby</span></div>
    <h1 class="wordmark">小樂點歌台</h1>
    <div class="brand-sub">Siao Le Jukebox · Pi Shield</div>
  </div>

  <div class="layout">
    <div class="col col-left">
      <div class="panel" id="deck-panel">
        <div class="deck-stage" id="deck-stage">
          <div class="halo">
            <div class="bloom"></div>
            <div class="shock"></div>
            <div class="ring r2"></div>
            <div class="ring r1"></div>
          </div>
          <div class="deck" id="deck">
            <div class="deck-base"></div>
            <div class="deck-etch">小樂點歌台<small>ANALOG REQUEST DECK</small></div>
            <div class="platter">
              <div class="record" id="record"><div class="rec-label"></div></div>
            </div>
            <div class="tonearm" id="tonearm">
              <div class="arm"></div><div class="pivot"></div><div class="head"></div>
            </div>
            <div class="deck-leds" id="deck-leds"><i></i><i></i></div>
          </div>
        </div>

        <div class="np" id="now-playing"><div class="np-title muted">等待點歌中</div></div>
        <div class="bar"><i id="progress-bar"></i></div>
        <div class="clock"><span id="clock-now">0:00</span><span id="clock-end">--:--</span></div>

        <div class="row">
          <button class="btn on" id="pause-btn" onclick="togglePause()">⏸ 暫停</button>
          <button class="btn" onclick="skip()">⏭ 切歌</button>
        </div>
        <div class="row">
          <button class="btn" onclick="setMode('original')">🎤 原聲</button>
          <button class="btn on-mint" onclick="setMode('instrumental')">🎹 伴奏</button>
        </div>
      </div>

      <div class="lyrics-float" id="lyrics"><div class="ly">目前沒有播放</div></div>

      <div class="panel">
        <div class="label">音場<span class="tally" id="live-tag" style="display:none">LIVE</span></div>
        <div class="vu" id="vu"></div>
        <div class="vol-row">
          <span class="ic">🔈</span>
          <input type="range" class="vol" id="vol" min="0" max="100" step="1" value="75"
                 aria-label="音量" oninput="onVolInput(this.value)" onchange="onVolCommit(this.value)" />
          <span class="ic">🔊</span>
          <span class="vol-num" id="vol-val">75%</span>
        </div>
      </div>
    </div>

    <div class="col col-right">
      <div class="panel">
        <div class="label">點歌</div>
        <div class="field">
          <span class="ic">🔍</span>
          <input id="song-input" type="text" placeholder="輸入歌名或 YouTube 網址"
                 autocomplete="off" enterkeyhint="send" />
        </div>
        <div class="hint" id="type-hint"></div>
        <div class="seg">
          <button id="mode-original" class="btn on" onclick="selectMode('original')">🎤 原聲</button>
          <button id="mode-instrumental" class="btn" onclick="selectMode('instrumental')">🎹 伴奏</button>
        </div>
        <button class="cta" onclick="addSong()">加入排隊</button>
      </div>

      <div class="panel">
        <div class="label">頻道</div>
        <div class="radio-now" id="radio-status">目前沒有在隨機播放</div>
        <div class="radio-row">
          <button id="radio-kpop" class="rbtn kpop" onclick="startRadio('kpop')"><span class="em">💜</span>K-pop</button>
          <button id="radio-cpop" class="rbtn cpop" onclick="startRadio('cpop')"><span class="em">🏮</span>中文流行</button>
          <button id="radio-epop" class="rbtn epop" onclick="startRadio('epop')"><span class="em">🎧</span>英文流行</button>
        </div>
        <div class="row"><button class="btn" onclick="stopRadio()">⏸ 暫停頻道</button></div>
      </div>

      <div class="panel">
        <div class="label">待播<span class="tally" id="queue-count"></span></div>
        <div id="queue-list"><div class="empty">排隊中沒有歌曲</div></div>
      </div>

      <div class="panel">
        <div class="label">播過<span class="tally" id="history-count"></span></div>
        <div id="history-list"><div class="empty">還沒有播放紀錄</div></div>
      </div>
    </div>
  </div>
  </div>

<script>
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let selectedMode = 'original';
let currentLyrics = null;
let currentLyricsTitle = null;
let vuPlaying = false;

/* 全域指標狀態，星空、唱盤、面板高光共用同一份 */
const P = {x: -9999, y: -9999, has: false, burst: 0};

/* ================= 節拍源 =================
   ⚠️ 音訊是在樹莓派上解碼、從喇叭出來的，瀏覽器拿不到那條音訊串流，
   所以這裡「不可能」做真正的頻譜分析。這是一個跟著播放狀態走的固定節拍：
   播放中才跳、暫停就停。光圈震波與 VU 錶讀同一個 BEAT，兩者看起來才會同步。
   若之後真的要跟著音樂，唯一可行的路是開瀏覽器麥克風用 Web Audio 收環境音。 */
const BEAT = {kick: 0, pulse: 1, phase: 0};
const BPM = 100;

function initBeat() {
  const stage = document.getElementById('deck-stage');
  if (reduceMotion) { setInterval(tickVU, 420); return; }
  let last = performance.now(), vuAcc = 0;
  (function loop(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    BEAT.kick *= Math.pow(0.015, dt);              /* 每秒衰減到 1.5% */
    if (vuPlaying) {
      BEAT.phase += dt * BPM / 60;
      if (BEAT.phase >= 1) { BEAT.phase -= 1; BEAT.kick = 1; BEAT.pulse = 0; }
      BEAT.pulse = Math.min(1, BEAT.pulse + dt * 1.7);
    } else {
      BEAT.phase = 0; BEAT.pulse = 1;
    }
    stage.style.setProperty('--beat', BEAT.kick.toFixed(3));
    stage.style.setProperty('--pulse', BEAT.pulse.toFixed(3));
    vuAcc += dt;
    if (vuAcc >= 0.09) { vuAcc = 0; tickVU(); }
    requestAnimationFrame(loop);
  })(last);
}

/* ================= 天蠍（線描插畫） =================
   使用者要的是星座卡上那隻「畫出來的」蠍子，不是星點連線的天文星圖。
   所以這裡是參數化的線描：頭胸甲 + 七節腹部 + 兩支大螯 + 八隻腳
   + 捲起來的尾巴與毒針，另外散幾顆四芒星呼應卡片風格。
   座標以「整體寬度約 1」為單位，畫的時候 ctx.scale(S, S)，
   所以線寬要除以 S 補回來，否則會被一起放大。                    */
const ART = {
  carapace: [[0,-0.260],[0.070,-0.245],[0.098,-0.190],[0.100,-0.120],[0.078,-0.070],[0,-0.055],
             [-0.078,-0.070],[-0.100,-0.120],[-0.098,-0.190],[-0.070,-0.245]],
  meso: [[0.092,-0.060],[0.096,0.000],[0.090,0.060],[0.078,0.120],[0.060,0.175],[0.038,0.218],
         [0,0.238],
         [-0.038,0.218],[-0.060,0.175],[-0.078,0.120],[-0.090,0.060],[-0.096,0.000],[-0.092,-0.060]],
  ribs: [[-0.005,0.095],[0.055,0.090],[0.113,0.079],[0.168,0.062],[0.212,0.042]],
  /* 尾巴繞到腳的外側（最遠 x=0.408 > 腳的 0.352），才不會跟腳纏在一起 */
  tail: [[0,0.238],[0.086,0.300],[0.196,0.324],[0.300,0.294],[0.376,0.216],
         [0.408,0.112],[0.396,0.006],[0.348,-0.086],[0.276,-0.160],[0.198,-0.208]],
  telson: [[0.238,-0.196],[0.260,-0.244],[0.234,-0.288],[0.180,-0.294],[0.150,-0.250],[0.172,-0.202]],
  sting: [[0.212,-0.290],[0.198,-0.344],[0.158,-0.386]],
  /* 八隻腳一律往下外扇開，不往上跟大螯搶位置 */
  legs: [[[0.098,-0.135],[0.190,-0.150],[0.280,-0.120],[0.330,-0.145]],
         [[0.098,-0.100],[0.200,-0.086],[0.300,-0.036],[0.352,-0.048]],
         [[0.098,-0.065],[0.200,-0.020],[0.296,0.048],[0.344,0.048]],
         [[0.098,-0.030],[0.192,0.048],[0.278,0.126],[0.322,0.142]]],
  armA: [[0.086,-0.252],[0.190,-0.298],[0.286,-0.330]],
  armB: [[0.286,-0.330],[0.362,-0.360],[0.418,-0.364]],
  hand: [[0.400,-0.386],[0.470,-0.426],[0.548,-0.416],[0.582,-0.366],
         [0.552,-0.318],[0.470,-0.312],[0.414,-0.342]],
  /* 鉗子的識別點是那個 V 形開口：中段兩指相距 0.096，約是指寬的三倍，
     尖端才收到 0.018。上一版兩指只差 0.026，管寬幾乎把縫隙填滿，
     整支就併成一片刀鋒，看起來像觸鬚不像螯。                        */
  fingA: [[0.566,-0.398],[0.660,-0.448],[0.742,-0.478]],
  fingB: [[0.552,-0.320],[0.652,-0.352],[0.740,-0.460]],
  eyes: [[0.022,-0.165],[0.062,-0.222]],
  sparks: [[-0.78,0.12,0.032],[0.76,0.30,0.024],[-0.40,0.44,0.020],
           [0.30,-0.58,0.028],[-0.66,-0.50,0.018],[0.10,0.48,0.016]]
};



/* 用中點做二次貝茲，讓折線變成平滑曲線 */
function pSmooth(ctx, pts, close) {
  const n = pts.length;
  ctx.beginPath();
  if (close) {
    ctx.moveTo((pts[n - 1][0] + pts[0][0]) / 2, (pts[n - 1][1] + pts[0][1]) / 2);
    for (let i = 0; i < n; i++) {
      const p = pts[i], q = pts[(i + 1) % n];
      ctx.quadraticCurveTo(p[0], p[1], (p[0] + q[0]) / 2, (p[1] + q[1]) / 2);
    }
    ctx.closePath();
  } else {
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < n - 1; i++) {
      const p = pts[i], q = pts[i + 1];
      ctx.quadraticCurveTo(p[0], p[1], (p[0] + q[0]) / 2, (p[1] + q[1]) / 2);
    }
    ctx.lineTo(pts[n - 1][0], pts[n - 1][1]);
  }
}

/* 沿著跟 pSmooth 完全一致的曲線重新取樣。
   ⚠️ 這個一定要做：tubeSides 若只吃 3 個控制點，外框只有 6 個點，
   pSmooth 平滑後會把它抹成一顆橢圓——螯臂就變成一串 blob 而不是漸縮的肢節。*/
function sampleOpen(pts, n) {
  const m = pts.length;
  if (m < 3) return pts.slice();
  const segs = [];
  let start = pts[0];
  for (let i = 1; i < m - 1; i++) {
    const end = [(pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2];
    segs.push([start, pts[i], end]);
    start = end;
  }
  segs.push([start, start, pts[m - 1]]);
  const out = [];
  for (let k = 0; k <= n; k++) {
    const u = (k / n) * segs.length;
    const si = Math.min(segs.length - 1, Math.floor(u)), tt = u - si;
    const a = segs[si][0], c = segs[si][1], b = segs[si][2], it = 1 - tt;
    out.push([it * it * a[0] + 2 * it * tt * c[0] + tt * tt * b[0],
              it * it * a[1] + 2 * it * tt * c[1] + tt * tt * b[1]]);
  }
  return out;
}

/* 沿著中線往兩側偏移，做出會漸縮的管狀外框 */
function tubeSides(pts, w0, w1) {
  const n = pts.length, L = [], R = [];
  for (let i = 0; i < n; i++) {
    const p = pts[i], q = pts[Math.min(n - 1, i + 1)], o = pts[Math.max(0, i - 1)];
    let dx = q[0] - o[0], dy = q[1] - o[1];
    const d = Math.hypot(dx, dy) || 1;
    dx /= d; dy /= d;
    const w = (w0 + (w1 - w0) * (i / (n - 1))) / 2;
    L.push([p[0] - dy * w, p[1] + dx * w]);
    R.push([p[0] + dy * w, p[1] - dx * w]);
  }
  return {L: L, R: R};
}
function mirror(pts, s) {
  const out = [];
  for (let i = 0; i < pts.length; i++) out.push([pts[i][0] * s, pts[i][1]]);
  return out;
}
function sparkle(ctx, x, y, r) {
  ctx.beginPath();
  ctx.moveTo(x, y - r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.quadraticCurveTo(x, y, x, y + r);
  ctx.quadraticCurveTo(x, y, x - r, y);
  ctx.quadraticCurveTo(x, y, x, y - r);
  ctx.fill();
}

function drawScorpion(ctx, W, H, t) {
  const S = Math.min(W * 0.44, H * 0.62);
  const cx = W / 2 + (P.has ? (P.x - W / 2) * 0.016 : 0);
  const cy = H / 2 + (P.has ? (P.y - H / 2) * 0.016 : 0);
  const A = ART;
  const tailSd = tubeSides(A.tail, 0.082, 0.034);

  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(Math.sin(t * 0.05) * 0.035);
  ctx.scale(S, S);
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';

  const base = 0.42 + BEAT.kick * 0.30;
  /* 兩趟：第一趟粗而淡當光暈，第二趟細而清楚 */
  for (let pass = 0; pass < 2; pass++) {
    const w = (pass === 0 ? 6.0 : 1.7) / S;
    const a = pass === 0 ? base * 0.12 : base;
    ctx.lineWidth = w;
    ctx.strokeStyle = 'rgba(214,226,255,' + a.toFixed(3) + ')';
    ctx.fillStyle = 'rgba(214,226,255,' + a.toFixed(3) + ')';

    for (let s = -1; s <= 1; s += 2) {
      for (let k = 0; k < A.legs.length; k++) {       /* 腳做成會漸縮的管，才有重量 */
        const lg = tubeSides(sampleOpen(mirror(A.legs[k], s), 22), 0.030, 0.010);
        pSmooth(ctx, lg.L.concat(lg.R.slice().reverse()), true); ctx.stroke();
      }
      const sa = tubeSides(sampleOpen(mirror(A.armA, s), 20), 0.062, 0.054);
      pSmooth(ctx, sa.L.concat(sa.R.slice().reverse()), true); ctx.stroke();
      const sb = tubeSides(sampleOpen(mirror(A.armB, s), 20), 0.056, 0.050);
      pSmooth(ctx, sb.L.concat(sb.R.slice().reverse()), true); ctx.stroke();
      pSmooth(ctx, mirror(A.hand, s), true); ctx.stroke();
      const fa = tubeSides(sampleOpen(mirror(A.fingA, s), 20), 0.032, 0.006);   /* 鉗子的兩根指 */
      pSmooth(ctx, fa.L.concat(fa.R.slice().reverse()), true); ctx.stroke();
      const fb = tubeSides(sampleOpen(mirror(A.fingB, s), 20), 0.030, 0.006);
      pSmooth(ctx, fb.L.concat(fb.R.slice().reverse()), true); ctx.stroke();
    }

    pSmooth(ctx, A.meso, true); ctx.stroke();
    for (let i = 0; i < A.ribs.length; i++) {          /* 腹部體節 */
      ctx.beginPath();
      ctx.moveTo(-A.ribs[i][1], A.ribs[i][0]);
      ctx.lineTo(A.ribs[i][1], A.ribs[i][0]);
      ctx.stroke();
    }
    pSmooth(ctx, A.carapace, true); ctx.stroke();

    /* 尾巴最後畫：蠍子的尾巴是舉在背上的，本來就該蓋過腳和身體 */
    pSmooth(ctx, tailSd.L.concat(tailSd.R.slice().reverse()), true); ctx.stroke();
    for (let i = 1; i < A.tail.length - 1; i++) {      /* 尾節分界 */
      ctx.beginPath();
      ctx.moveTo(tailSd.L[i][0], tailSd.L[i][1]);
      ctx.lineTo(tailSd.R[i][0], tailSd.R[i][1]);
      ctx.stroke();
    }
    pSmooth(ctx, A.telson, true); ctx.stroke();
    const st = tubeSides(sampleOpen(A.sting, 18), 0.030, 0.002);       /* 毒針：漸縮成尖點 */
    pSmooth(ctx, st.L.concat(st.R.slice().reverse()), true); ctx.stroke();

    if (pass === 1) {
      for (let s = -1; s <= 1; s += 2) {
        for (let i = 0; i < A.eyes.length; i++) {
          ctx.beginPath();
          ctx.arc(A.eyes[i][0] * s, A.eyes[i][1], 0.013, 0, 6.283);
          ctx.fill();
        }
      }
      for (let i = 0; i < A.sparks.length; i++) {
        const sp = A.sparks[i];
        const tw = 0.45 + 0.55 * Math.sin(t * (0.9 + i * 0.21) + i * 1.7);
        ctx.fillStyle = 'rgba(232,240,255,' + (base * tw).toFixed(3) + ')';
        sparkle(ctx, sp[0], sp[1], sp[2] * (0.8 + tw * 0.4));
      }
    }
  }
  ctx.restore();
}

function selectMode(mode) {
  selectedMode = mode;
  document.getElementById('mode-original').classList.toggle('on', mode === 'original');
  document.getElementById('mode-instrumental').classList.toggle('on', mode === 'instrumental');
}

/* ================= 互動星空 =================
   每顆星有原點與速度，用彈簧拉回原點。游標會推開附近的星，
   點擊會炸開一圈。靠近游標的星會變亮變大並跟游標連線。      */
function initStars() {
  const cv = document.getElementById('stars');
  const ctx = cv.getContext('2d');
  const TINT = ['255,255,255', '127,168,217', '168,139,224', '230,143,200', '111,227,196'];
  const WEIGHT = [0, 0, 0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 4];   /* 白色最多，彩色點綴 */
  const R = 190, R2 = R * R;                                 /* 游標影響半徑 */
  let W = 0, H = 0, dpr = 1, stars = [], shoot = [], t = 0, nextShoot = 120;

  function build() {
    dpr = Math.min(2, window.devicePixelRatio || 1);
    W = window.innerWidth; H = window.innerHeight;
    cv.width = Math.floor(W * dpr); cv.height = Math.floor(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.round(Math.min(280, Math.max(110, W * H / 6200)));
    stars = [];
    for (let i = 0; i < n; i++) {
      const z = Math.random();                    /* 深度：影響視差與大小 */
      /* 極座標取樣並把半徑往外偏：中央留給天蠍座，星點集中在周邊 */
      const ang = Math.random() * 6.283;
      const rad = 0.34 + 0.70 * Math.pow(Math.random(), 0.5);
      const ox = Math.min(0.995, Math.max(0.005, 0.5 + Math.cos(ang) * rad * 0.62));
      const oy = Math.min(0.995, Math.max(0.005, 0.5 + Math.sin(ang) * rad * 0.68));
      stars.push({
        ox: ox, oy: oy, x: ox * W, y: oy * H, vx: 0, vy: 0, z: z,
        r: 0.65 + z * 1.85,
        a: 0.40 + z * 0.55,
        tint: TINT[WEIGHT[(Math.random() * WEIGHT.length) | 0]],
        tp: Math.random() * 6.283,
        ts: 0.6 + Math.random() * 1.6
      });
    }
  }
  build();
  window.addEventListener('resize', build, {passive: true});

  function draw() {
    ctx.clearRect(0, 0, W, H);
    drawScorpion(ctx, W, H, t);      /* 先畫，所以天蠍座在一般星點後面 */
    const parX = P.has ? (P.x - W / 2) * 0.022 : 0;
    const parY = P.has ? (P.y - H / 2) * 0.022 : 0;
    const near = [];

    for (let i = 0; i < stars.length; i++) {
      const s = stars[i];
      /* 彈簧拉回原點（含視差偏移） */
      const hx = s.ox * W + parX * s.z, hy = s.oy * H + parY * s.z;
      s.vx += (hx - s.x) * 0.014;
      s.vy += (hy - s.y) * 0.014;

      let dx = s.x - P.x, dy = s.y - P.y, d2 = dx * dx + dy * dy, glow = 0;
      if (P.has && d2 < R2) {
        const d = Math.sqrt(d2) || 1;
        glow = 1 - d / R;
        const push = glow * glow * (0.9 + P.burst * 9);   /* 點擊時推力放大 */
        s.vx += (dx / d) * push;
        s.vy += (dy / d) * push;
        if (near.length < 26) near.push(s);
      }
      s.vx *= 0.90; s.vy *= 0.90;
      s.x += s.vx; s.y += s.vy;

      const tw = 0.62 + 0.38 * Math.sin(t * s.ts + s.tp);
      const a = Math.min(1, s.a * tw + glow * 0.85 + BEAT.kick * 0.14);
      const r = s.r * (1 + glow * 1.9);
      ctx.beginPath();
      ctx.arc(s.x, s.y, r, 0, 6.283);
      ctx.fillStyle = 'rgba(' + s.tint + ',' + a.toFixed(3) + ')';
      ctx.fill();
      if (glow > 0.4 || (s.z > 0.72 && tw > 0.82)) {       /* 亮星加一圈暈 */
        ctx.beginPath();
        ctx.arc(s.x, s.y, r * 3.8, 0, 6.283);
        ctx.fillStyle = 'rgba(' + s.tint + ',' + (a * 0.15).toFixed(3) + ')';
        ctx.fill();
      }
    }

    /* 游標附近的星互相連線，形成星座 */
    ctx.lineWidth = 0.7;
    for (let i = 0; i < near.length; i++) {
      const a = near[i];
      const da = Math.hypot(a.x - P.x, a.y - P.y);
      ctx.strokeStyle = 'rgba(168,139,224,' + (0.28 * (1 - da / R)).toFixed(3) + ')';
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(P.x, P.y); ctx.stroke();
      for (let j = i + 1; j < near.length; j++) {
        const b = near[j], dd = Math.hypot(a.x - b.x, a.y - b.y);
        if (dd > 96) continue;
        ctx.strokeStyle = 'rgba(127,168,217,' + (0.20 * (1 - dd / 96)).toFixed(3) + ')';
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
    }

    /* 流星 */
    if (--nextShoot <= 0) {
      nextShoot = 260 + Math.random() * 520;
      shoot.push({x: Math.random() * W * 0.7, y: Math.random() * H * 0.4,
                  vx: 5 + Math.random() * 4, vy: 2.2 + Math.random() * 1.8, life: 1});
    }
    for (let i = shoot.length - 1; i >= 0; i--) {
      const m = shoot[i];
      m.x += m.vx; m.y += m.vy; m.life -= 0.014;
      if (m.life <= 0) { shoot.splice(i, 1); continue; }
      const g = ctx.createLinearGradient(m.x, m.y, m.x - m.vx * 13, m.y - m.vy * 13);
      g.addColorStop(0, 'rgba(255,255,255,' + (m.life * 0.85).toFixed(3) + ')');
      g.addColorStop(1, 'rgba(168,139,224,0)');
      ctx.strokeStyle = g; ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.moveTo(m.x, m.y);
      ctx.lineTo(m.x - m.vx * 13, m.y - m.vy * 13); ctx.stroke();
    }

    P.burst *= 0.88;
    t += 0.016;
    if (!reduceMotion) requestAnimationFrame(draw);
  }
  draw();
}

/* ================= 指標：星空 / 唱盤 / 面板高光 ================= */
function initPointer() {
  if (reduceMotion) return;
  const deck = document.getElementById('deck');
  let ty = 0, tz = 0, cy = 0, cz = 0;

  window.addEventListener('pointermove', function (e) {
    if (e.pointerType === 'touch') return;
    P.x = e.clientX; P.y = e.clientY; P.has = true;
    const p = e.target && e.target.closest ? e.target.closest('.panel') : null;
    if (p) {
      const r = p.getBoundingClientRect();
      p.style.setProperty('--mx', (e.clientX - r.left) + 'px');
      p.style.setProperty('--my', (e.clientY - r.top) + 'px');
    }
    ty = (e.clientX / window.innerWidth - 0.5) * 26;    /* 唱盤左右擺 */
    tz = (e.clientY / window.innerHeight - 0.5) * -16;  /* 唱盤前後轉 */
  }, {passive: true});

  document.addEventListener('pointerleave', function () { P.has = false; ty = 0; tz = 0; });
  window.addEventListener('pointerdown', function (e) {
    P.x = e.clientX; P.y = e.clientY; P.has = true; P.burst = 1;   /* 星星炸開 */
  }, {passive: true});

  /* 用 rAF 補間，避免 CSS transition 造成的黏滯感 */
  (function tilt() {
    cy += (ty - cy) * 0.075; cz += (tz - cz) * 0.075;
    deck.style.setProperty('--ry', cy.toFixed(2) + 'deg');
    deck.style.setProperty('--rz', cz.toFixed(2) + 'deg');
    requestAnimationFrame(tilt);
  })();
}

/* ================= 背景聲波 ================= */
function initWave() {
  if (reduceMotion) return;
  const cv = document.getElementById('wave');
  const ctx = cv.getContext('2d');
  const COLORS = ['rgba(127,168,217,.55)', 'rgba(168,139,224,.50)', 'rgba(111,227,196,.34)'];
  let w = 0, h = 0, t = 0, amp = 0.22;

  function resize() {
    /* 刻意用低解析度畫布再拉滿版：外層有 blur，看不出來，但省很多填充率 */
    w = cv.width = Math.max(320, Math.min(760, Math.floor(window.innerWidth / 2)));
    h = cv.height = 190;
  }
  resize();
  window.addEventListener('resize', resize, {passive: true});

  (function draw() {
    amp += ((vuPlaying ? 1 : 0.22) - amp) * 0.04;
    ctx.clearRect(0, 0, w, h);
    ctx.lineWidth = 2.4;
    for (let k = 0; k < 3; k++) {
      ctx.beginPath();
      ctx.strokeStyle = COLORS[k];
      const f = 0.011 + k * 0.006, sp = 0.9 + k * 0.5, a = (26 - k * 5) * amp;
      for (let x = 0; x <= w; x += 4) {
        const y = h * (0.5 + k * 0.09)
                + Math.sin(x * f + t * sp) * a
                + Math.sin(x * f * 2.3 + t * sp * 1.6) * a * 0.4;
        if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    t += 0.02;
    requestAnimationFrame(draw);
  })();
}

/* ---------- 中文輸入法友善的 Enter ---------- */
let composing = false, justComposed = false;
function initInput() {
  const input = document.getElementById('song-input');
  const hint = document.getElementById('type-hint');
  input.addEventListener('compositionstart', function () {
    composing = true; hint.textContent = '選字中… 打完再按 Enter';
  });
  input.addEventListener('compositionend', function () {
    composing = false; justComposed = true;
    hint.textContent = '按 Enter 或點下面的按鈕加入排隊';
    setTimeout(function () { justComposed = false; }, 120);
  });
  input.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    if (composing || e.isComposing || e.keyCode === 229 || justComposed) return;
    e.preventDefault(); addSong();
  });
  input.addEventListener('input', function () {
    if (!composing) hint.textContent = input.value ? '按 Enter 或點下面的按鈕加入排隊' : '';
  });
}

/* ---------- 音量 ---------- */
let volTimer = null, volDragging = false;
function onVolInput(v) {
  volDragging = true;
  document.getElementById('vol-val').textContent = v + '%';
  clearTimeout(volTimer);
  volTimer = setTimeout(function () { sendVolume(v); }, 180);
}
function onVolCommit(v) { clearTimeout(volTimer); sendVolume(v); }
function sendVolume(v) {
  fetch('/api/karaoke/volume', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({volume: Number(v)})
  }).finally(function () { setTimeout(function () { volDragging = false; }, 400); });
}

/* ---------- VU ---------- */
const VU_BARS = 34;
function initVU() {
  let html = '';
  for (let i = 0; i < VU_BARS; i++) html += '<span></span>';
  document.getElementById('vu').innerHTML = html;
}
function tickVU() {
  const vu = document.getElementById('vu');
  const bars = vu.children;
  /* 重拍時整排一起竄高，所以 VU 跟光圈看起來是同一個節奏 */
  const env = 0.46 + BEAT.kick * 0.66;
  for (let i = 0; i < bars.length; i++) {
    let hh = 8;
    if (vuPlaying) {
      const centre = 1 - Math.abs(i - (VU_BARS - 1) / 2) / ((VU_BARS - 1) / 2);
      hh = 10 + Math.min(86, Math.random() * 92 * (0.28 + centre * 0.72) * env);
    }
    bars[i].style.height = hh.toFixed(0) + '%';
  }
  vu.classList.toggle('on', vuPlaying);
}

function setLive(playing, hasSong) {
  vuPlaying = !!playing;
  const air = document.getElementById('on-air');
  air.classList.toggle('live', !!playing);
  document.getElementById('on-air-text').textContent =
    playing ? 'On Air' : (hasSong ? 'Paused' : 'Standby');
  document.getElementById('live-tag').style.display = playing ? '' : 'none';
  document.getElementById('deck-stage').classList.toggle('live', !!playing);
  document.getElementById('tonearm').classList.toggle('on', !!playing);
  const leds = document.getElementById('deck-leds').children;
  leds[0].classList.toggle('on', !!playing);
  leds[1].classList.toggle('on', !!hasSong);
}
function setCount(id, n) {
  const el = document.getElementById(id);
  if (el) el.textContent = n > 0 ? n : '';
}
function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s == null ? '' : s;
  return div.innerHTML;
}
function fmtTime(sec) {
  if (sec == null) return '--:--';
  sec = Math.floor(sec);
  return Math.floor(sec / 60) + ':' + String(sec % 60).padStart(2, '0');
}

function renderNowPlaying(data) {
  const np = data.now_playing;
  const el = document.getElementById('now-playing');
  const record = document.getElementById('record');
  const pauseBtn = document.getElementById('pause-btn');
  if (!np) {
    el.innerHTML = '<div class="np-title muted">等待點歌中</div>';
    document.getElementById('progress-bar').style.width = '0%';
    document.getElementById('clock-now').textContent = '0:00';
    document.getElementById('clock-end').textContent = '--:--';
    record.classList.remove('spinning');
    pauseBtn.textContent = '⏸ 暫停';
    pauseBtn.classList.remove('on-mint');
    pauseBtn.classList.add('on');
    setLive(false, false);
    return;
  }
  record.classList.toggle('spinning', !data.paused);
  pauseBtn.textContent = data.paused ? '▶️ 繼續' : '⏸ 暫停';
  pauseBtn.classList.toggle('on-mint', !!data.paused);
  pauseBtn.classList.toggle('on', !data.paused);
  setLive(!data.paused, true);
  const isInst = np.mode === 'instrumental';
  el.innerHTML = '<div class="np-title">' + escapeHtml(np.title) + '</div>' +
    '<div class="np-sub"><span class="chip' + (isInst ? ' alt' : '') + '">' +
    (isInst ? '伴奏版' : '原聲') + '</span><span>' + escapeHtml(np.requester) + '</span></div>';
  const pct = data.duration ? Math.min(100, (data.time_pos / data.duration) * 100) : 0;
  document.getElementById('progress-bar').style.width = pct + '%';
  document.getElementById('clock-now').textContent = fmtTime(data.time_pos);
  document.getElementById('clock-end').textContent = fmtTime(data.duration);
}

function renderVolume(vol) {
  if (vol == null || volDragging) return;
  const slider = document.getElementById('vol');
  if (document.activeElement === slider) return;
  slider.value = vol;
  document.getElementById('vol-val').textContent = vol + '%';
}

function renderLyrics(lyrics, timePos) {
  const el = document.getElementById('lyrics');
  if (!lyrics || lyrics.length === 0) {
    el.innerHTML = '<div class="ly">（沒有找到歌詞）</div>';
    return;
  }
  let idx = -1;
  for (let i = 0; i < lyrics.length; i++) {
    if (lyrics[i].time <= (timePos || 0)) idx = i; else break;
  }
  const start = Math.max(0, idx - 2), end = Math.min(lyrics.length, idx + 4);
  let html = '';
  for (let i = start; i < end; i++) {
    const cls = i === idx ? 'ly cur' : (Math.abs(i - idx) === 1 ? 'ly near' : 'ly');
    html += '<div class="' + cls + '">' + escapeHtml(lyrics[i].text) + '</div>';
  }
  el.innerHTML = html;
}

function renderQueue(queue) {
  const el = document.getElementById('queue-list');
  setCount('queue-count', queue ? queue.length : 0);
  if (!queue || queue.length === 0) {
    el.innerHTML = '<div class="empty">排隊中沒有歌曲</div>';
    return;
  }
  let html = '';
  queue.forEach(function (s, i) {
    html += '<div class="item">' +
      '<div class="idx">' + (i + 1) + '</div>' +
      '<div class="it-info"><div class="it-title">' + escapeHtml(s.query) + '</div>' +
      '<div class="it-sub">' + (s.mode === 'instrumental' ? '伴奏' : '原聲') + ' · ' +
      escapeHtml(s.requester) + '</div></div>' +
      '<button class="mini" title="插隊" onclick="priority(\\'' + s.id + '\\')">⬆</button>' +
      '<button class="mini del" title="移除" onclick="removeSong(\\'' + s.id + '\\')">✕</button>' +
      '</div>';
  });
  el.innerHTML = html;
}

function renderHistory(history) {
  const el = document.getElementById('history-list');
  setCount('history-count', history ? history.length : 0);
  if (!history || history.length === 0) {
    el.innerHTML = '<div class="empty">還沒有播放紀錄</div>';
    return;
  }
  let html = '';
  history.forEach(function (h) {
    html += '<div class="item hist" onclick="replaySong(\\'' + h.url + '\\', \\'' + h.mode + '\\')">' +
      '<div class="idx play">♪</div>' +
      '<div class="it-info"><div class="it-title">' + escapeHtml(h.title) + '</div>' +
      '<div class="it-sub">' + (h.mode === 'instrumental' ? '伴奏' : '原聲') + ' · ' +
      escapeHtml(h.requester) + '</div></div>' +
      '<button class="mini again" title="再播一次" onclick="event.stopPropagation(); replaySong(\\'' +
      h.url + '\\', \\'' + h.mode + '\\')">🔁</button>' +
      '</div>';
  });
  el.innerHTML = html;
}

function replaySong(url, mode) {
  fetch('/api/karaoke/add', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({query: url, mode: mode, requester: '網頁點歌'})
  }).then(poll);
}

const RADIO_LABELS = {kpop: 'K-pop', cpop: '中文流行', epop: '英文流行'};
function renderRadio(category) {
  document.getElementById('radio-status').textContent =
    category ? ('🔀 隨機播放中：' + RADIO_LABELS[category]) : '目前沒有在隨機播放';
  ['kpop', 'cpop', 'epop'].forEach(function (c) {
    document.getElementById('radio-' + c).classList.toggle('on', c === category);
  });
}

function poll() {
  fetch('/api/karaoke/status').then(function (r) { return r.json(); }).then(function (data) {
    renderNowPlaying(data);
    renderVolume(data.volume);
    renderQueue(data.queue);
    renderHistory(data.history);
    renderRadio(data.radio_category);
    if (data.now_playing) {
      if (currentLyricsTitle !== data.now_playing.title) {
        currentLyrics = data.lyrics;
        currentLyricsTitle = data.now_playing.title;
      }
      renderLyrics(currentLyrics, data.time_pos);
    } else {
      currentLyrics = null; currentLyricsTitle = null;
      document.getElementById('lyrics').innerHTML = '<div class="ly">目前沒有播放</div>';
    }
  }).catch(function () {});
}

function startRadio(category) {
  fetch('/api/karaoke/radio', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({category: category})
  }).then(poll);
}
function stopRadio() { fetch('/api/karaoke/radio/stop', {method: 'POST'}).then(poll); }

function addSong() {
  const input = document.getElementById('song-input');
  const query = input.value.trim();
  if (!query) return;
  fetch('/api/karaoke/add', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({query: query, mode: selectedMode, requester: '網頁點歌'})
  }).then(function () {
    input.value = '';
    document.getElementById('type-hint').textContent = '';
    poll();
  });
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
function skip() { fetch('/api/karaoke/skip', {method: 'POST'}).then(poll); }
function togglePause() {
  const btn = document.getElementById('pause-btn');
  const willPause = !btn.classList.contains('on-mint');
  btn.textContent = willPause ? '▶️ 繼續' : '⏸ 暫停';
  btn.classList.toggle('on-mint', willPause);
  btn.classList.toggle('on', !willPause);
  fetch('/api/karaoke/pause', {method: 'POST'}).then(poll).catch(poll);
}
function setMode(mode) {
  fetch('/api/karaoke/mode', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({mode: mode})
  }).then(poll);
}

initVU();
initBeat();
initStars();
initPointer();
initWave();
initInput();
poll();
setInterval(poll, 1500);
</script>
</body>
</html>
"""

DISPLAY_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>小樂點歌台 · 大螢幕</title>
<style>
  :root {
    --bg-a: #0a0818; --bg-b: #160e2e; --bg-c: #0c1622;
    --text: #f5f3ff; --sub: #8f89b3;
    --brand: linear-gradient(135deg, #8b7cf6, #ff6fa0);
    --brand2: linear-gradient(135deg, #06b6d4, #22c55e);
    --card: rgba(255,255,255,.05);
    --card-border: rgba(255,255,255,.08);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body {
    width: 100%; height: 100%; overflow: hidden;
    background:
      radial-gradient(circle at 15% 10%, var(--bg-b) 0%, transparent 45%),
      radial-gradient(circle at 88% 20%, var(--bg-c) 0%, transparent 40%),
      var(--bg-a);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif;
  }
  .stage {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    width: 100vw; height: 100vh; padding: 4vh 6vw; text-align: center;
  }

  /* ---- idle state ---- */
  .idle { display: flex; flex-direction: column; align-items: center; gap: 2vh; }
  .idle .emoji { font-size: 10vw; opacity: .8; }
  .idle h1 {
    font-size: 4vw; font-weight: 800;
    background: var(--brand); -webkit-background-clip: text; background-clip: text; color: transparent;
  }
  .idle p { font-size: 1.6vw; color: var(--sub); }

  /* ---- now playing header ---- */
  .np-head { display: flex; align-items: center; gap: 2.2vw; margin-bottom: 3vh; }
  .vinyl {
    width: 9vw; height: 9vw; min-width: 70px; min-height: 70px; border-radius: 50%; flex-shrink: 0;
    background: conic-gradient(from 0deg, #8b7cf6, #ff6fa0, #ffb86f, #8b7cf6);
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 0 60px rgba(139,124,246,.5);
  }
  .vinyl::after { content: ''; width: 32%; height: 32%; border-radius: 50%; background: var(--bg-a); }
  .vinyl.spinning { animation: spin 5s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .np-text { text-align: left; }
  .np-title {
    font-size: 3vw; font-weight: 800; line-height: 1.25; max-width: 70vw;
    overflow: hidden; text-overflow: ellipsis; display: -webkit-box;
    -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  }
  .np-sub { font-size: 1.3vw; color: var(--sub); margin-top: .8vh; }
  .pill {
    display: inline-block; padding: .3vh 1vw; border-radius: 999px;
    font-size: 1.1vw; font-weight: 700; color: #fff; background: var(--brand);
    margin-right: 8px;
  }
  .pill.alt { background: var(--brand2); }

  /* ---- lyrics ---- */
  .lyrics { display: flex; flex-direction: column; gap: 2.2vh; width: 100%; max-width: 90vw; }
  .lyric-line { font-size: 2vw; color: var(--sub); opacity: .45; transition: all .3s; line-height: 1.4; }
  .lyric-line.current {
    font-size: 4.2vw; font-weight: 800; opacity: 1; line-height: 1.3;
    background: var(--brand); -webkit-background-clip: text; background-clip: text; color: transparent;
  }

  /* ---- progress ---- */
  .progress-wrap { width: 60vw; max-width: 900px; margin-top: 4vh; }
  .progress-track { background: rgba(255,255,255,.1); border-radius: 8px; height: 10px; overflow: hidden; }
  .progress-bar { background: var(--brand); height: 100%; width: 0%; border-radius: 8px; transition: width .3s linear; }

  /* ---- up next strip ---- */
  .up-next {
    position: fixed; left: 0; right: 0; bottom: 0;
    display: flex; align-items: center; gap: 1.4vw;
    padding: 2vh 3vw; background: linear-gradient(to top, rgba(0,0,0,.55), transparent);
  }
  .up-next .label {
    font-size: 1.1vw; font-weight: 800; color: var(--sub); text-transform: uppercase; letter-spacing: .1em;
    flex-shrink: 0;
  }
  .up-next .item {
    font-size: 1.3vw; font-weight: 600; color: var(--text); opacity: .85;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    background: var(--card); border: 1px solid var(--card-border);
    padding: .8vh 1.2vw; border-radius: 999px;
  }

  /* ---- corner hint ---- */
  .hint {
    position: fixed; top: 2.5vh; right: 3vw; text-align: right;
    font-size: 1vw; color: var(--sub); line-height: 1.6;
  }
  .hint b { color: var(--text); }
</style>
</head>
<body>
  <div class="hint">在 LINE 傳 <b>「點歌 歌名」</b> 就能加入排隊<br />或說口語的也聽得懂，例如「我想聽稻香」</div>

  <div class="stage" id="stage">
    <div class="idle" id="idle-view">
      <div class="emoji">🎤</div>
      <h1>等待點歌中...</h1>
      <p>在 LINE 傳「點歌 歌名」開始今晚的第一首歌</p>
    </div>

    <div id="playing-view" style="display:none; width:100%;">
      <div class="np-head">
        <div class="vinyl" id="vinyl"></div>
        <div class="np-text">
          <div class="np-title" id="np-title"></div>
          <div class="np-sub" id="np-sub"></div>
        </div>
      </div>
      <div class="lyrics" id="lyrics"></div>
      <div class="progress-wrap">
        <div class="progress-track"><div class="progress-bar" id="progress-bar"></div></div>
      </div>
    </div>
  </div>

  <div class="up-next" id="up-next" style="display:none;">
    <div class="label">接下來</div>
  </div>

<script>
let currentLyrics = null;
let currentLyricsTitle = null;

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s == null ? '' : s;
  return div.innerHTML;
}

function renderLyrics(lyrics, timePos) {
  const el = document.getElementById('lyrics');
  if (!lyrics || lyrics.length === 0) {
    el.innerHTML = '<div class="lyric-line current">🎶</div>';
    return;
  }
  let idx = -1;
  for (let i = 0; i < lyrics.length; i++) {
    if (lyrics[i].time <= (timePos || 0)) idx = i; else break;
  }
  const start = Math.max(0, idx - 1);
  const end = Math.min(lyrics.length, idx + 3);
  let html = '';
  for (let i = start; i < end; i++) {
    const cls = i === idx ? 'lyric-line current' : 'lyric-line';
    html += '<div class="' + cls + '">' + escapeHtml(lyrics[i].text) + '</div>';
  }
  el.innerHTML = html;
}

function renderUpNext(queue) {
  const wrap = document.getElementById('up-next');
  if (!queue || queue.length === 0) {
    wrap.style.display = 'none';
    return;
  }
  wrap.style.display = 'flex';
  let html = '<div class="label">接下來</div>';
  queue.slice(0, 4).forEach(function (s) {
    html += '<div class="item">' + escapeHtml(s.title || s.query) + '</div>';
  });
  wrap.innerHTML = html;
}

function poll() {
  fetch('/api/karaoke/status').then(function (r) { return r.json(); }).then(function (data) {
    const np = data.now_playing;
    const idleView = document.getElementById('idle-view');
    const playingView = document.getElementById('playing-view');
    if (!np) {
      idleView.style.display = 'flex';
      playingView.style.display = 'none';
      renderUpNext(data.queue);
      currentLyrics = null;
      currentLyricsTitle = null;
      return;
    }
    idleView.style.display = 'none';
    playingView.style.display = 'block';
    document.getElementById('vinyl').classList.add('spinning');
    document.getElementById('np-title').textContent = np.title;
    const modeLabel = np.mode === 'instrumental' ? '伴奏版' : '原聲';
    const pillClass = np.mode === 'instrumental' ? 'pill alt' : 'pill';
    document.getElementById('np-sub').innerHTML =
      '<span class="' + pillClass + '">' + modeLabel + '</span>' + escapeHtml(np.requester) + ' 點播';
    const pct = data.duration ? Math.min(100, (data.time_pos / data.duration) * 100) : 0;
    document.getElementById('progress-bar').style.width = pct + '%';
    if (currentLyricsTitle !== np.title) {
      currentLyrics = data.lyrics;
      currentLyricsTitle = np.title;
    }
    renderLyrics(currentLyrics, data.time_pos);
    renderUpNext(data.queue);
  }).catch(function () {});
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
<title>小樂點歌台 操作手冊</title>
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
  <h1>🎤 小樂點歌台 操作手冊</h1>
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
  <div class="card">
    更口語的方式：直接 <code>@隨便什麼稱呼 歌名</code>，跟「點歌」完全一樣，只是感覺像在叫機器人：<br />
    <code>@小樂 稻香</code>
    <div class="sub">@ 後面接的稱呼不會被檢查是不是正確，隨便打都算數，重點是後面那個空白隔開的歌名。</div>
  </div>

  <h2>不知道歌名？請它推薦</h2>
  <div class="card">
    <code>推薦 &lt;歌手或關鍵字&gt;</code>（也可以說「介紹 X」「X的歌」「X有什麼歌」「X推薦」）<br />
    例如：<code>推薦 周杰倫</code><br />
    <span class="sub">機器人會列出搜尋到的前 5 首熱門歌曲，回一個數字（1~5）就會直接把那首加入排隊，不用再打一次歌名。這個「回數字」的視窗有效期是 2 分鐘，超過的話數字鍵就會變回原本的燈泡控制指令。</span>
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
    <span class="sub">現正播放、進度條、動態同步歌詞、點歌輸入框、排隊列表（可以頂歌/刪除）、熱門歌曲隨機播放按鈕、已播歌曲紀錄都在這一頁，手機 LINE 內建瀏覽器打開就能用，每 1.5 秒自動更新一次。</span>
  </div>
  <div class="card">
    頁面最下面的「已播歌曲」會列出最近播過的歌，點整列或按 🔁 就能直接重新加入排隊——重播的是當初解析好的確切影片，不會重新搜尋選到不同版本。<br />
    <span class="sub">另外，「推薦 &lt;歌手&gt;」跟「熱門」電台自動選歌，都會自動排除 12 小時內播過的歌曲（同一首歌就算是不同人上傳、影片網址不一樣，也算重複），避免一直繞回同幾首；但直接「點歌」指定歌名的話，就算 12 小時內剛播過也一定會播，不受這個限制。已播紀錄超過 12 小時會自動清除，釋放記憶體，同時代表那些歌又可以被推薦/電台選到了。</span>
  </div>

  <h2>大螢幕模式（接電視/投影機）</h2>
  <div class="card">
    <a href="/display">/display</a><br />
    <span class="sub">專門給電視/顯示器看的大字版面，深色背景、超大字體的同步歌詞（像跑馬燈提詞機），加上現正播放的封面動畫跟接下來排隊的歌曲。用 LINE 傳 <code>大螢幕</code> 可以拿到這個連結，把樹莓派用 HDMI 接電視/顯示器，瀏覽器打開這頁就能當KTV的大螢幕用，讓大家一起看歌詞唱，不用各自盯著手機。</span>
  </div>

  <h2>聽不懂固定格式也沒關係</h2>
  <div class="card">
    以上指令都比對不到的話，機器人會試著用口語理解你的意思，例如「我想聽周杰倫的稻香」「可以跳過這首嗎」「先暫停一下音樂」都聽得懂，不用照著上面的固定格式打。
    <div class="sub">這個功能需要背後的本機 AI 服務有開著才會生效，沒開的話這類口語訊息還是會回「不認識的指令」，不影響上面列出的所有固定指令。</div>
  </div>

  <h2>用語音點歌</h2>
  <div class="card">
    在 LINE 直接錄一段語音訊息傳過去就可以，不用打字，例如直接說「我想聽稻香」。機器人會把語音轉成文字（一樣是用本機的服務轉，不會把你的聲音傳到雲端），回覆會先顯示「聽到你說：『...』」讓你確認有沒有聽錯，接著才是實際的處理結果。
    <div class="sub">如果聽錯了，直接再傳一次語音或改用打字都可以。這個功能跟上面的口語理解共用背後的本機服務，需要服務有開著才會生效。</div>
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


def _download_line_audio(message_id: str) -> bytes | None:
    try:
        resp = requests.get(
            f'https://api-data.line.me/v2/bot/message/{message_id}/content',
            headers={'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.content
    except requests.RequestException:
        pass
    return None


def _handle_voice_message(message_id: str, base_url: str, user_id) -> str:
    """語音訊息走的路：下載音檔 -> 本機 Whisper 轉文字 -> 丟回 handle_command()
    走一般文字指令（含既有規則跟 NLU fallback），跟打字點歌是同一套邏輯，
    只是多了語音轉文字這一步。回覆會附上聽到的內容，方便使用者發現辨識錯誤。"""
    audio_bytes = _download_line_audio(message_id)
    if not audio_bytes:
        return '語音訊息下載失敗，麻煩再傳一次'
    text = stt.transcribe(audio_bytes)
    if not text:
        return '沒聽清楚你說的話，可以再說一次，或直接打字'
    action_reply = handle_command(text, base_url=base_url, user_id=user_id)
    return f'🎤 聽到你說：「{text}」\n\n{action_reply}'


_display_name_cache: dict = {}


def get_display_name(user_id):
    if not user_id:
        return '匿名'
    if user_id in _display_name_cache:
        return _display_name_cache[user_id]
    # 只有成功查到名字才寫入快取——之前這裡不管成功失敗都會寫入，
    # 如果剛好那一次 LINE API 逾時/網路不穩，這個使用者就會被永久卡成「匿名」
    # 直到服務重啟，之後每次點歌都查不到真名。失敗的話這次先回「匿名」，
    # 但不快取，下次同一個人再點歌會重新試著查一次。
    try:
        resp = requests.get(
            f'https://api.line.me/v2/bot/profile/{user_id}',
            headers={'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'},
            timeout=8,
        )
        if resp.status_code == 200:
            name = resp.json().get('displayName')
            if name:
                _display_name_cache[user_id] = name
                return name
    except requests.RequestException:
        pass
    return '匿名'


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


def _queue_song_from_text(query_text: str, user_id) -> str:
    """共用邏輯：解析歌名尾綴 0（伴奏版），加入排隊，組回覆文字。"""
    query = query_text.strip()
    mode = 'original'
    if not query.startswith(('http://', 'https://')) and query.endswith('0') and len(query) > 1:
        query = query[:-1].strip()
        mode = 'instrumental'
    requester = get_display_name(user_id)
    karaoke.add_song(query, requester, mode)
    mode_label = '伴奏版' if mode == 'instrumental' else '原聲'
    return f'🎤 已加入點歌佇列（{mode_label}）：{query}\n點歌人：{requester}'


# user_id -> {'songs': [{'title':..., 'id':...}, ...], 'ts': float}
# 用來記住「剛剛推薦過的歌手候選清單」，讓使用者回一個數字就能直接點歌，
# 120 秒內有效、用過即丟；過期或沒有待選清單時，數字鍵一律照舊是 LED 指令。
_pending_recommendations: dict = {}
_RECOMMENDATION_TTL = 120


def _extract_recommend_keyword(key: str):
    """辨識「推薦 X」「介紹 X」「X的歌」「X有什麼歌」「X推薦」幾種自然說法，回傳關鍵字或 None。"""
    for prefix in ('推薦', '介紹'):
        if key.startswith(prefix):
            kw = key[len(prefix):].strip()
            if kw:
                return kw
    for suffix in ('有什麼歌', '的歌', '推薦'):
        if key.endswith(suffix) and len(key) > len(suffix):
            kw = key[:-len(suffix)].strip()
            if kw:
                return kw
    return None


def handle_command(text: str, base_url: str = '', user_id: str = None) -> str:
    key = text.strip()
    lowered = key.lower()
    panel_url = f'{base_url}/panel' if base_url else ''
    karaoke_url = f'{base_url}/karaoke' if base_url else ''
    manual_url = f'{base_url}/manual' if base_url else ''
    display_url = f'{base_url}/display' if base_url else ''

    # 剛推薦過歌手候選清單、且還在有效期內時，數字 1~5 用來選歌而不是控制燈泡。
    # 沒有待選清單時完全不影響原本的 LED 數字指令。
    pending = _pending_recommendations.get(user_id or '_anon')
    if pending and key in ('1', '2', '3', '4', '5') and time.time() - pending['ts'] < _RECOMMENDATION_TTL:
        _pending_recommendations.pop(user_id or '_anon', None)
        idx = int(key) - 1
        songs = pending['songs']
        if 0 <= idx < len(songs):
            song = songs[idx]
            requester = get_display_name(user_id)
            # 推薦功能給的是 video id；常點歌曲是從資料庫來的，可能只有查詢字串。
            # 兩種都要能點，所以有 id 就用精確網址，沒有就用原本的查詢字串。
            target = (f'https://www.youtube.com/watch?v={song["id"]}' if song.get('id')
                      else song.get('query') or song['title'])
            karaoke.add_song(target, requester, 'original')
            return f'🎤 已加入點歌佇列：{song["title"]}\n點歌人：{requester}'

    if '小樂' in key and '點歌' in key:
        if not base_url:
            return '點歌頁面連結目前無法產生'
        return f"🎤 歡迎收聽小樂點歌台！\n點歌頁面：{karaoke_url}\n操作手冊：{manual_url}\n\n快速上手：直接傳「點歌 歌名」就能加入排隊囉！"
    # ---- 常點歌曲（快捷點歌）----
    # 沿用推薦功能那套「回數字選歌」的機制：把清單暫存起來，
    # 使用者回 1~5 就直接點。**不另外發明一套互動方式**，
    # 使用者不必記兩種操作。
    if key in ('常點', '我的常點', '我常點的', '常點歌曲'):
        requester = get_display_name(user_id)
        top = song_stats.top_for(requester, limit=5)
        if not top:
            return f'{requester} 還沒有點歌紀錄喔，點過幾首之後這裡就會列出你最常點的歌。'
        _pending_recommendations[user_id or '_anon'] = {
            'songs': [{'id': None, 'title': t['title'], 'query': t['query']} for t in top],
            'ts': time.time(),
        }
        lines = [f'🎵 {requester} 最常點的歌：']
        for i, t in enumerate(top, 1):
            lines.append(f'{i}. {t["title"][:38]}（點過 {t["n"]} 次）')
        lines.append('\n回覆數字 1~5 直接點播')
        return '\n'.join(lines)

    if key in ('熱門排行', '排行', '排行榜', '大家常點'):
        top = song_stats.top_overall(limit=5)
        if not top:
            return '還沒有足夠的點歌紀錄。'
        _pending_recommendations[user_id or '_anon'] = {
            'songs': [{'id': None, 'title': t['title'], 'query': t['query']} for t in top],
            'ts': time.time(),
        }
        lines = ['🏆 大家最常點的歌：']
        for i, t in enumerate(top, 1):
            lines.append(f'{i}. {t["title"][:38]}（{t["n"]} 次）')
        lines.append('\n回覆數字 1~5 直接點播')
        return '\n'.join(lines)

    # ---- 天氣 ----
    if key in ('天氣', '氣溫', '溫度', '天氣如何', '現在天氣') or lowered == 'weather':
        return weather.report()

    # ---- 風扇（紅外線）----
    if key in ('開風扇', '風扇開', '打開風扇', '開電風扇'):
        return ir_remote.send('fan_power', '風扇')
    if key in ('關風扇', '風扇關', '關掉風扇', '關電風扇'):
        return ir_remote.send('fan_power', '風扇')
    if key in ('風扇風速', '調風速', '風速'):
        return ir_remote.send('fan_speed', '風速')
    if key in ('風扇擺頭', '擺頭', '搖頭'):
        return ir_remote.send('fan_swing', '擺頭')

    if lowered in ('面板', 'panel', '控制台'):
        return f"點這個連結打開圖形控制面板：\n{panel_url}" if panel_url else '面板連結目前無法產生'
    if lowered in ('大螢幕', '大屏', '投影', 'display', 'tv'):
        return f"用電視/顯示器打開這個連結（HDMI 接樹莓派）：\n{display_url}\n\n畫面會跟著現正播放自動更新，適合接投影機/電視當大家一起看的歌詞牆。" if display_url else '大螢幕頁面連結目前無法產生'
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

    # ---------- 小樂點歌台 ----------
    if key.startswith('點歌') or key.startswith('播放'):
        query = key[2:].strip()
        if not query:
            return '請在「點歌」後面加上歌名，例如：點歌 小星星（尾綴加0表示伴奏版，例如：點歌 小星星0）'
        return _queue_song_from_text(query, user_id)
    if lowered.startswith('play'):
        query = key[len('play'):].strip()
        if not query:
            return 'Usage: play <song name or YouTube URL>'
        return _queue_song_from_text(query, user_id)
    if key.startswith('@'):
        rest = key[1:].strip()
        parts = rest.split(None, 1)  # 第一個空白前是「叫誰」，不檢查內容，任何稱呼都接受
        if len(parts) == 2 and parts[1].strip():
            return _queue_song_from_text(parts[1], user_id)
        hint = f"\n點歌頁面：{karaoke_url}" if karaoke_url else ''
        return f'我在的～直接說「@我 歌名」就能點歌，或傳「排隊」看目前清單。{hint}'
    recommend_keyword = _extract_recommend_keyword(key)
    if recommend_keyword:
        songs = karaoke.search_top_songs(
            recommend_keyword, count=5,
            exclude_ids=karaoke.get_played_video_ids(),
            exclude_title_keys=karaoke.get_played_title_keys(),
        )
        if not songs:
            return f'找不到「{recommend_keyword}」的推薦歌曲，可以試試「點歌 {recommend_keyword} <歌名>」直接點播'
        _pending_recommendations[user_id or '_anon'] = {'songs': songs, 'ts': time.time()}
        lines = [f'🔍 「{recommend_keyword}」熱門推薦：']
        for i, s in enumerate(songs, 1):
            lines.append(f'{i}. {s["title"]}')
        lines.append('\n回覆數字（例如 1）就能直接加入排隊')
        return '\n'.join(lines)
    if lowered in ('排隊', '查詢', 'queue', '歌單'):
        return _format_queue_text()
    if lowered in ('暫停', '暫停播放', 'pause', '暫停音樂'):
        state = karaoke.toggle_pause()
        if state is None:
            return '目前沒有播放中的歌曲'
        return '⏸ 已暫停（傳「繼續」接著播）' if state else '▶️ 已繼續播放'
    if lowered in ('繼續', '繼續播放', 'resume', 'play', '播放繼續'):
        if karaoke.set_pause(False):
            return '▶️ 已繼續播放'
        return '目前沒有播放中的歌曲'
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

    # ---------- 自然語言翻譯（最後手段，比對不到任何既有規則才會用到） ----------
    # translate() 只會回傳既有指令格式的文字（或 None），所以直接遞迴丟回
    # handle_command() 讓前面所有規則重新處理一次，不用另外寫一套分派邏輯；
    # 翻譯結果如果還是比對不到任何規則，遞迴那次會直接落到下面的「不認識的指令」，
    # 不會再呼叫一次翻譯，天然不會無限迴圈。
    translated = nlu.translate(key)
    if translated:
        return handle_command(translated, base_url=base_url, user_id=user_id)
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
        msg_type = message.get('type')
        if msg_type == 'text':
            reply_text = handle_command(message.get('text', ''), base_url=base_url, user_id=user_id)
        elif msg_type == 'audio':
            reply_text = _handle_voice_message(message.get('id'), base_url=base_url, user_id=user_id)
        else:
            continue
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


@app.route('/display', methods=['GET'])
def display_page():
    return DISPLAY_HTML


@app.route('/manual', methods=['GET'])
def manual_page():
    return MANUAL_HTML


@app.route('/api/voice', methods=['POST'])
def api_voice():
    """給 voice_control.py（麥克風語音控制守護程式）用的入口。

    刻意只收「已經去掉喚醒詞的純指令文字」，然後丟進跟 LINE 完全一樣的
    handle_command()——所有既有規則、@提及、推薦、NLU fallback 全部原封不動重用，
    語音跟打字走的是同一條路，不會有兩套行為不一致的問題。

    只開放給本機（127.0.0.1）呼叫，避免區網上任何人都能對麥克風端點下指令。
    """
    if request.remote_addr not in ('127.0.0.1', '::1'):
        return jsonify({'status': 'error', 'message': 'local only'}), 403
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'status': 'error', 'message': 'empty text'}), 400
    base_url = f"https://{request.host}"
    reply = handle_command(text, base_url=base_url, user_id=None)
    return jsonify({'status': 'ok', 'reply': reply})


@app.route('/api/karaoke/status', methods=['GET'])
def api_karaoke_status():
    status = karaoke.get_status()
    lyrics = None
    if status['now_playing']:
        np = status['now_playing']
        # 先用使用者輸入的乾淨歌名搜歌詞，YouTube 標題常常太雜亂（含頻道名稱等），當備援用
        lyrics = karaoke.fetch_lyrics(np['query'], np['title'])
    status['lyrics'] = lyrics
    status['history'] = karaoke.get_history(limit=20)
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


@app.route('/api/karaoke/pause', methods=['POST'])
def api_karaoke_pause():
    """暫停/繼續。不帶參數就是切換；帶 {"paused": true/false} 就是指定狀態。"""
    data = request.get_json(force=True, silent=True) or {}
    if 'paused' in data:
        ok = karaoke.set_pause(bool(data['paused']))
        return jsonify({'status': 'ok' if ok else 'error', 'paused': bool(data['paused'])})
    state = karaoke.toggle_pause()
    if state is None:
        return jsonify({'status': 'error', 'message': 'nothing playing'}), 400
    return jsonify({'status': 'ok', 'paused': state})


@app.route('/api/karaoke/volume', methods=['POST'])
def api_karaoke_volume():
    data = request.get_json(force=True, silent=True) or {}
    if 'volume' not in data:
        return jsonify({'status': 'error', 'message': 'missing volume'}), 400
    ok = karaoke.set_volume(data['volume'])
    return jsonify({'status': 'ok' if ok else 'error', 'volume': karaoke.get_volume()})


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
