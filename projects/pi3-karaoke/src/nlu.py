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
import re

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
「常點」「熱門排行」「天氣」「切歌」「停止」這幾個是完整指令，前面絕對不可以加「點歌」兩個字。
使用者如果有講歌手名，一定要把歌手名跟歌名一起保留（例如「我想聽周杰倫的告白氣球」要輸出
「點歌 周杰倫 告白氣球」，不可以只輸出「點歌 告白氣球」）——歌手名會讓搜尋結果準很多，不能省略。

重要：使用者的話可能是「語音辨識」轉出來的，常常有同音字錯誤。
如果聽起來像某首知名歌曲的歌名，請自動更正成正確的歌名再輸出。例如：
道香 / 到香 / 到響 / 到聲 -> 稻香
告白汽球 / 告白氣求 -> 告白氣球
晴天娃娃（在點歌情境下）-> 晴天
溫柔鄉 -> 溫柔
不確定的話就照使用者原本講的輸出，不要亂改成完全不相干的歌。
只有「使用者明確講出一首歌的歌名」時才可以用「點歌 <歌名>」。
問「我常點什麼」是要查自己的紀錄，不是要點一首叫「常點」的歌。
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
常點
熱門排行
天氣
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
今天天氣如何 -> 天氣
外面會不會下雨 -> 天氣
現在幾度 -> 天氣
我最常點哪些歌 -> 常點
我平常都唱什麼 -> 常點
我常點什麼 -> 常點
查一下我的點歌紀錄 -> 常點
大家最愛點什麼歌 -> 熱門排行
現在最紅的是哪首 -> 熱門排行
你叫什麼名字 -> 無法辨識
你好 -> 無法辨識
"""


# qwen3 是 reasoning 模型，預設每次回答前都會先產生一大段 thinking。
# 指令翻譯這種短任務完全不需要，而且慢到會逾時——實測同一句話：
#   有 thinking：27.8 秒（reasoning_tokens 311）
#   加 /no_think：2.8 秒（reasoning_tokens 1）
# openclaw 的 chat_template_kwargs.enable_thinking=false 在這條路徑上沒生效，
# 用 qwen3 原生的 /no_think 前綴才真的關得掉。
_NO_THINK = '/no_think '

# 模型平常熱著的時候大約 3 秒。但如果 LM Studio 把模型從記憶體卸載了
# （閒置太久或 Mac 重開機後第一次呼叫），會需要重新載入約 19 秒，
# 所以逾時要留夠，不然第一個使用者一定失敗。
_TIMEOUT = 25

# 萬一模型還是吐了 thinking 區塊，把它濾掉再判斷
_THINK_BLOCK = re.compile(r'<think>.*?</think>', re.DOTALL)


def translate(text: str) -> str | None:
    if not NLU_ENABLED or not NLU_BASE_URL or not NLU_TOKEN:
        return None
    body = {
        'model': 'openclaw/karaoke-nlu',
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': _NO_THINK + text},
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
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        content = resp.json()['choices'][0]['message']['content']
        content = _THINK_BLOCK.sub('', content or '').strip()
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return None
    if not content or content == '無法辨識':
        return None
    return content
