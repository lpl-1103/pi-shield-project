#!/usr/bin/env python3
"""
本機語音轉文字服務：接收音訊檔案，回傳辨識出的文字。

給樹莓派的 LINE 機器人呼叫，把使用者傳的語音訊息轉成文字，再丟進既有的
handle_command() 走一般文字指令（含 NLU fallback）的路——這裡只負責「聽懂」，
不做任何指令判斷。跟 openclaw/NLU 那組完全獨立，不需要 openclaw 也能跑。
"""
import os
import tempfile
import wave

import mlx_whisper
import numpy as np
from flask import Flask, jsonify, request
from scipy.signal import butter, sosfilt

MODEL = 'mlx-community/whisper-large-v3-turbo'

# 不指定語言的話 whisper 會自己猜，實測收音稍微不清楚就會猜成英文、
# 吐出「Every remark remark remark」這種完全無關的英文亂碼。
# 這個系統的使用者只講中文，直接鎖定，辨識穩很多。
LANGUAGE = 'zh'

# initial_prompt 是給 whisper 的「這段音訊大概會出現什麼詞」的提示，
# 對專有名詞（歌名、歌手名）幫助很大——例如沒有提示時「稻香」會被聽成「到響」。
# 這裡放喚醒詞 + 常用指令 + 常見歌手，讓它優先往這些詞去對。
INITIAL_PROMPT = (
    '以下是卡拉OK點歌系統的語音指令。'
    '常見說法：小P、點歌、切歌、停止、原聲、伴奏、排隊、推薦、熱門、常點、天氣。'
    '常見歌手：周杰倫、五月天、林俊傑、陳奕迅、鄧紫棋、蔡依林、張惠妹、孫燕姿、王力宏。'
    '常見歌名：稻香、告白氣球、晴天、溫柔、倔強、江南、富士山下、光年之外。'
)

HIGHPASS_HZ = 250
# 樹莓派那支 USB 麥克風的噪音幾乎全在 300Hz 以下——實測 0~100Hz 的能量是
# 人聲頻段（300~1000Hz）的 30 倍。那是電源/接地之類的低頻隆隆聲，不是寬頻嘶聲。
# 砍掉它可以拿掉絕大部分噪音能量，而人聲清晰度主要在 300~3400Hz，完全不受影響。
# 手機錄的 LINE 語音訊息本來就乾淨，濾一下也無害。


def preprocess_wav(path: str) -> bool:
    """對 WAV 做高通濾波 + 正規化。不是 WAV（例如 LINE 的 m4a）就跳過。"""
    try:
        with wave.open(path, 'rb') as w:
            if w.getsampwidth() != 2:
                return False
            rate, ch = w.getframerate(), w.getnchannels()
            x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
        if ch > 1:
            x = x.reshape(-1, ch).mean(axis=1)
        if len(x) < rate // 10:
            return False
        sos = butter(4, HIGHPASS_HZ, 'highpass', fs=rate, output='sos')
        y = sosfilt(sos, x)
        peak = np.abs(y).max()
        if peak > 0:
            y = y * (0.9 * 32767 / peak)      # 正規化，讓音量落在 whisper 習慣的範圍
        with wave.open(path, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(np.clip(y, -32768, 32767).astype(np.int16).tobytes())
        return True
    except Exception:
        return False      # 前處理失敗就用原檔，不要因此整個辨識失敗


app = Flask(__name__)


@app.route('/transcribe', methods=['POST'])
def transcribe():
    audio_bytes = request.get_data()
    if not audio_bytes:
        return jsonify({'error': 'empty body'}), 400
    fd, path = tempfile.mkstemp(suffix='.m4a')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(audio_bytes)
        preprocess_wav(path)
        result = mlx_whisper.transcribe(
            path,
            path_or_hf_repo=MODEL,
            language=LANGUAGE,
            initial_prompt=INITIAL_PROMPT,
        )
        text = (result.get('text') or '').strip()
        return jsonify({'text': text})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500
    finally:
        os.unlink(path)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'model': MODEL})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8765)
