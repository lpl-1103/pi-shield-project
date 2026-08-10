#!/usr/bin/env python3
"""
語音轉文字：把 LINE 語音訊息的音訊丟給 Mac 上跑的本機 Whisper 服務（mlx-whisper）轉成文字。

跟 nlu.py 是平行的獨立模組，風格一致：只匯出一個函式，任何失敗（服務沒開、逾時、
格式不對）一律回 None，呼叫端看到 None 就知道「沒聽懂」，自己決定怎麼回覆使用者。
跟 openclaw 完全無關，是另一個獨立的本機服務。
"""

from __future__ import annotations

import json
import os

import requests

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pi3_line_config.json')

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    _config = json.load(f)

STT_ENABLED = _config.get('stt_enabled', False)
STT_BASE_URL = _config.get('stt_base_url', '')


def transcribe(audio_bytes: bytes) -> str | None:
    if not STT_ENABLED or not STT_BASE_URL or not audio_bytes:
        return None
    try:
        resp = requests.post(
            f'{STT_BASE_URL}/transcribe',
            data=audio_bytes,
            headers={'Content-Type': 'audio/m4a'},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        text = (resp.json().get('text') or '').strip()
    except (requests.RequestException, ValueError, KeyError):
        return None
    return text or None
