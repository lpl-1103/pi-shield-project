#!/usr/bin/env python3
"""
語音控制守護程式（麥克風實體開關 = 說話按鈕）

使用者要的流程非常單純：
    打開麥克風 -> 講話 -> 關掉麥克風 -> 系統執行指令 -> 音樂繼續放

所以「關掉麥克風」就是**說完了**的訊號，不用靠靜音偵測去猜什麼時候講完
（之前用 VAD 猜，換氣就被判定講完、歌名被切掉，還會被喇叭的音樂誤觸發）。
這支麥克風的實體開關會讓整個 USB 裝置從系統消失，所以「錄音串流中斷」
就是明確的結束訊號，比任何音量門檻都可靠。

流程：
    等 USB 麥克風出現（= 使用者打開開關）
      -> 自動設定增益（USB 重新列舉會把增益歸零，每次都要重設）
      -> 一直錄，全部存起來
      -> 串流中斷（= 使用者關掉開關）
      -> 把整段丟給 Mac 的 whisper 轉文字
      -> 有喚醒詞就剝掉（沒有也沒關係，開麥克風本身就是意圖）
      -> POST 給 line_control 的 /api/voice 執行

刻意不裝 numpy / pyaudio / sounddevice：這台是最小化安裝，
Python 3.13 也把 audioop 移除了，用 struct + 純 Python 就夠。
"""

from __future__ import annotations

import io
import json
import math
import os
import re
import struct
import subprocess
import threading
import time
import wave

import requests

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pi3_line_config.json')

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    _config = json.load(f)

STT_BASE_URL = _config.get('stt_base_url', '')
LOCAL_API = _config.get('voice_local_api', 'http://127.0.0.1:8000')

RATE = 16000          # whisper 就是吃 16k
CHANNELS = 1
SAMPLE_WIDTH = 2      # S16_LE
CHUNK_BYTES = int(RATE * 0.1) * SAMPLE_WIDTH * CHANNELS

MIC_GAIN = 8          # 起始值。實測：0 太小辨識失敗，14+AGC 會削波失真，8 是不錯的起點
GAIN_MIN, GAIN_MAX = 2, 14
GAIN_STATE = os.path.expanduser('~/.voice_mic_gain')
# 增益會自動調整：講話大小聲、離麥克風遠近都會影響音量。
# 削波（振幅頂到 32767）會嚴重破壞辨識——實測削波時「我要聽稻香」被聽成
# 「我要聽到香了」。太小聲同樣辨識不出來。所以每次錄完看峰值自動修正。
CLIP_PEAK = 30000     # 超過就算削波，要降增益
QUIET_PEAK = 4000     # 低於就算太小聲，要升增益
MIN_SPEECH_SEC = 0.5  # 開關按太快（不到半秒）當作誤觸，不送辨識
MAX_SPEECH_SEC = 60   # 忘記關麥克風的保險，錄到這麼長就先送出去

# 喚醒詞是「可選的」——打開麥克風本身就代表要下指令了。
# 有講就剝掉，沒講也照樣執行。whisper 聽「小P」寫法不固定，多種變體都認。
_WAKE_RE = re.compile(r'^\s*(小\s*[PpＰｐ]|小批|小皮|小屁|小披|曉批|小逼)\s*[,，。、!！?？~～]*\s*')


def log(msg):
    print(f'[voice] {msg}', flush=True)   # systemd 底下不 flush 會看不到即時 log


def detect_capture_device():
    """找 USB 麥克風。

    注意兩件事：
    1. 要比對「整行」——card 4 的短名稱是 `Device`，只有整行才有
       `[USB PnP Sound Device]` 這個線索。
    2. **絕不退回 WM8960**：那片板子的麥克風實測是純靜音（振幅恆為 0），
       拿它當備援只會讓程式看起來在跑、實際永遠聽不到聲音。
    """
    try:
        out = subprocess.run(['arecord', '-l'], capture_output=True, text=True, timeout=10).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    for line in out.splitlines():
        m = re.match(r'\s*card (\d+): (.+)', line)
        if not m:
            continue
        idx, desc = m.group(1), m.group(2).strip()
        if 'wm8960' in desc.lower():
            continue
        return f'plughw:{idx},0', desc
    return None


def load_gain() -> int:
    try:
        with open(GAIN_STATE) as f:
            return max(GAIN_MIN, min(GAIN_MAX, int(f.read().strip())))
    except (OSError, ValueError):
        return MIC_GAIN


def save_gain(g: int):
    try:
        with open(GAIN_STATE, 'w') as f:
            f.write(str(g))
    except OSError:
        pass


def adapt_gain(peak: int):
    """根據上一段錄音的峰值自動修正增益，下次就會比較剛好。"""
    g = load_gain()
    if peak >= CLIP_PEAK and g > GAIN_MIN:
        new = max(GAIN_MIN, g - 2)
        log(f'⚠ 音量削波（峰值 {peak}），增益 {g} -> {new}')
        save_gain(new)
    elif peak < QUIET_PEAK and g < GAIN_MAX:
        new = min(GAIN_MAX, g + 2)
        log(f'音量偏小（峰值 {peak}），增益 {g} -> {new}')
        save_gain(new)


def configure_mic(device: str):
    """設定增益。**每次 USB 重新插入 ALSA 設定都會重設**（實測增益歸零），
    所以每次接上都要重設，不能只設一次。"""
    m = re.search(r'plughw:(\d+)', device)
    if not m:
        return
    card = m.group(1)
    gain = load_gain()
    for args in (['sset', 'Auto Gain Control', 'off'],   # AGC 會削波，關掉
                 ['sset', 'Mic', str(gain), 'unmute']):
        try:
            subprocess.run(['amixer', '-c', card] + args, capture_output=True, timeout=10)
        except (subprocess.SubprocessError, OSError):
            pass
    log(f'麥克風增益設定為 {gain}')


def to_wav_bytes(frames: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(RATE)
        w.writeframes(frames)
    return buf.getvalue()


# 頭尾各修掉這麼多。只要夠蓋掉開關的「喀」聲就好——
# 一開始設 0.35 秒太貪心：1.6 秒的錄音被切掉近一半，
# 使用者的聲音可能整段被切進去，反而害辨識失敗。
EDGE_TRIM_SEC = 0.15


def trim_edges(frames: bytes) -> bytes:
    """把錄音頭尾各切掉一小段。

    使用者是用實體開關控制錄音，**撥動開關的「喀」聲會被錄進去**，
    而且是極短的full-scale 尖峰——實測某段錄音峰值 31889（看起來像爆音），
    但 95% 的音量其實只有 4399，代表爆的是開關聲不是人聲。
    這個尖峰會（1）害自動增益誤判成講太大聲而調低（2）干擾 whisper 辨識。
    """
    cut = int(RATE * EDGE_TRIM_SEC) * SAMPLE_WIDTH
    if len(frames) <= cut * 2 + RATE * SAMPLE_WIDTH // 2:
        return frames        # 太短就不修，不然會沒東西剩
    return frames[cut:-cut]


def peak_of(frames: bytes) -> int:
    n = len(frames) // 2
    if n == 0:
        return 0
    return max(abs(x) for x in struct.unpack('<%dh' % n, frames[:n * 2]))


def looks_hallucinated(text: str) -> bool:
    """whisper 對著雜訊會硬編出重複迴圈，例如 '張張張張…'、'比例比例比例…'。"""
    if not text:
        return True
    s = re.sub(r'[\s,，。、!！?？~～.]+', '', text)
    if len(s) < 4:
        return False
    if len(s) >= 20 and len(set(s)) / len(s) < 0.25:
        return True
    for ch in set(s):
        if len(s) >= 10 and s.count(ch) / len(s) > 0.5:
            return True
    return False


def transcribe(frames: bytes) -> str | None:
    if not STT_BASE_URL:
        return None
    try:
        resp = requests.post(
            f'{STT_BASE_URL}/transcribe',
            data=to_wav_bytes(frames),
            headers={'Content-Type': 'audio/wav'},
            timeout=60,
        )
        if resp.status_code != 200:
            return None
        return (resp.json().get('text') or '').strip()
    except (requests.RequestException, ValueError, KeyError):
        return None


def run_command(text: str) -> str | None:
    try:
        resp = requests.post(f'{LOCAL_API}/api/voice', json={'text': text}, timeout=90)
        if resp.status_code != 200:
            return None
        return resp.json().get('reply')
    except (requests.RequestException, ValueError):
        return None


RECORD_DIR = os.path.expanduser('~/voice_recordings')
KEEP_RECORDINGS = 10


def save_recording(frames: bytes) -> str | None:
    """留最近幾段錄音，方便事後拿真實音檔調辨識參數，
    不用每改一次設定就麻煩使用者重講一次。"""
    try:
        os.makedirs(RECORD_DIR, exist_ok=True)
        path = os.path.join(RECORD_DIR, time.strftime('%Y%m%d-%H%M%S') + '.wav')
        with open(path, 'wb') as f:
            f.write(to_wav_bytes(frames))
        old = sorted(os.listdir(RECORD_DIR))
        for name in old[:-KEEP_RECORDINGS]:
            try:
                os.unlink(os.path.join(RECORD_DIR, name))
            except OSError:
                pass
        return path
    except OSError:
        return None


def process(frames: bytes, dur: float):
    """背景處理一段錄音：轉文字 -> 去喚醒詞 -> 執行。"""
    # **存原始未修剪的音訊**——診斷時要看得到完整內容。
    # 之前存修剪後的版本，害我一直在分析被自己切過的音檔，
    # 看到 0.68 秒純底噪還以為是麥克風沒收到聲音。
    saved = save_recording(frames)
    frames = trim_edges(frames)          # 再去掉開關的喀聲，才量音量跟辨識
    peak = peak_of(frames)
    log(f'處理 {dur:.1f} 秒錄音（最大振幅 {peak}）{" 已存 " + os.path.basename(saved) if saved else ""}')
    adapt_gain(peak)          # 依這次的音量自動修正下次的增益
    if peak < 500:
        log('整段幾乎沒有聲音，跳過（麥克風是不是靜音了？）')
        return
    text = transcribe(frames)
    if not text:
        log('辨識不出內容')
        return
    if looks_hallucinated(text):
        log(f'（丟棄）疑似雜訊幻覺：{text[:30]!r}')
        return
    log(f'聽到：{text!r}')

    command = _WAKE_RE.sub('', text).strip()   # 有喚醒詞就剝掉，沒有就原樣用
    command = command.strip('，。、!！?？~～ ')
    if not command:
        log('只有喚醒詞，沒有指令內容')
        return

    log(f'-> 執行：{command!r}')
    log(f'<- 回覆：{run_command(command)!r}')


def record_session():
    """錄一次：等麥克風打開 -> 一直錄 -> 麥克風關掉就結束並回傳錄到的內容。"""
    dev = None
    waited = 0
    while not dev:
        dev = detect_capture_device()
        if dev:
            break
        if waited % 60 == 0:
            log('待機中——打開麥克風開關就開始收音')
        time.sleep(3)
        waited += 3

    device, desc = dev
    configure_mic(device)
    log(f'🎤 麥克風已開啟（{device}），請說話...')

    cmd = ['arecord', '-D', device, '-f', 'S16_LE', '-r', str(RATE),
           '-c', str(CHANNELS), '-t', 'raw', '-q']
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError as exc:
        log(f'啟動錄音失敗：{exc!r}')
        time.sleep(3)
        return None, 0.0

    frames = []
    started = time.time()
    while True:
        data = proc.stdout.read(CHUNK_BYTES)
        if not data:
            break                      # 串流中斷 = 使用者關掉麥克風 = 說完了
        frames.append(data)
        if time.time() - started >= MAX_SPEECH_SEC:
            log('錄太久了，先送出去辨識（忘記關麥克風？）')
            break
    try:
        proc.kill()
    except Exception:
        pass

    dur = time.time() - started
    log(f'🔇 麥克風已關閉，錄到 {dur:.1f} 秒')
    return b''.join(frames), dur


def main():
    log(f'語音辨識服務：{STT_BASE_URL}')
    log('使用方式：打開麥克風 -> 講話 -> 關掉麥克風，就會執行指令')
    while True:
        try:
            audio, dur = record_session()
            if not audio or dur < MIN_SPEECH_SEC:
                if audio is not None and dur:
                    log(f'只有 {dur:.1f} 秒，當作誤觸，忽略')
                # 等裝置節點真的消失，避免馬上又抓到同一個要斷不斷的裝置
                time.sleep(2)
                continue
            # 丟背景處理，主迴圈馬上回去等下一次開麥克風
            threading.Thread(target=process, args=(audio, dur), daemon=True).start()
            time.sleep(2)
        except Exception as exc:
            log(f'主迴圈異常：{exc!r}，3 秒後重試')
            time.sleep(3)


if __name__ == '__main__':
    main()
