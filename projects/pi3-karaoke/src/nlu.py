#!/usr/bin/env python3
"""
自然語言翻譯層：把使用者的口語需求丟給 Mac 上的 openclaw（karaoke-nlu agent，
模型是本機 Bionic/LM Studio 跑的本地模型），翻譯成點歌機器人既有的指令格式文字。

跟 line_control.py 是呼叫關係：handle_command() 比對不到任何既有規則時，
才會呼叫這裡的 translate()，拿到的文字會被重新丟回 handle_command() 處理，
所以這裡只需要負責「翻譯」，不需要知道任何實際動作怎麼執行。

任何失敗（連不到、逾時、格式不對、模型說無法辨識）一律回傳 None，
呼叫端看到 None 就當作「沒聽懂」，跟現在的行為一樣，不會讓機器人卡住或壞掉。
"""

from __future__ import annotations

import json
import os

import requests

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pi3_line_config.json')

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    _config = json.load(f)

NLU_ENABLED = _config.get('nlu_enabled', False)
NLU_BASE_URL = _config.get('nlu_base_url', '')
NLU_TOKEN = _config.get('nlu_token', '')

SYSTEM_PROMPT = """你是樹莓派點歌機器人的指令翻譯器。你的唯一工作是把使用者的口語需求，
轉換成下面列出的其中一種指令格式，原封不動輸出那一行，不要加任何其他文字、解釋、引號、標點符號。
只有使用者明確要求伴奏/去人聲時才加尾綴0，沒提到的話絕對不要加0。
如果使用者的話跟點歌系統完全無關，或你無法判斷對應哪個指令，就只輸出：無法辨識
絕對不要輸出跟燈泡、蜂鳴器、繼電器有關的指令，也不要自己推薦歌曲名稱或編造內容。

合法的指令格式只有這些：
點歌 <歌名>
切歌
停止
原聲
伴奏
排隊
推薦 <歌手或關鍵字>
熱門 kpop
熱門 中文
熱門 英文
暫停熱門
無法辨識

範例（輸入 -> 輸出，一定要照格式，不要多加字，指令本身不要加引號）：
我想聽周杰倫的稻香 -> 點歌 周杰倫 稻香
幫我點一首晴天 -> 點歌 晴天
我要伴奏版的小星星 -> 點歌 小星星0
可以跳過這首嗎 -> 切歌
換下一首 -> 切歌
先暫停一下音樂 -> 停止
換回原本有唱的版本 -> 原聲
我要聽人聲的版本 -> 原聲
換成沒有人聲的版本 -> 伴奏
有沒有推薦五月天的歌 -> 推薦 五月天
放一些韓文歌來聽 -> 熱門 kpop
今天天氣如何 -> 無法辨識
你叫什麼名字 -> 無法辨識
你好 -> 無法辨識
"""


def translate(text: str) -> str | None:
    if not NLU_ENABLED or not NLU_BASE_URL or not NLU_TOKEN:
        return None
    body = {
        'model': 'openclaw/karaoke-nlu',
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': text},
        ],
    }
    try:
        resp = requests.post(
            f'{NLU_BASE_URL}/v1/chat/completions',
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {NLU_TOKEN}',
            },
            data=json.dumps(body),
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        content = resp.json()['choices'][0]['message']['content'].strip()
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return None
    if not content or content == '無法辨識':
        return None
    return content
