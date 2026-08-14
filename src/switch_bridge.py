#!/usr/bin/env python3
"""把 Aqara 中樞收到的無線開關事件，轉成博聯小黑豆的紅外線發射。

    D1 無線開關 ──Zigbee──> Aqara 中樞 ──UDP 多播──> 這支 ──> 小黑豆 ──紅外──> 家電

## 為什麼需要這支

Aqara 跟博聯是兩個互不相通的生態系，Aqara App 沒有「控制博聯裝置」的選項。
中樞負責左半段（Zigbee 收開關），小黑豆負責右半段（發紅外），
中間這段翻譯沒有現成的東西可用，所以自己做。

## 對應規則放在 `~/switch_rules.json`

    {
      "158d0001abcdef": {              // D1 開關的 sid，用 aqara_discover.py 查
        "channel_0": {"click": "風扇電源"},
        "channel_1": {"click": "冷氣電源", "double_click": "冷氣強風"}
      }
    }

值是**已經學過的紅外碼名稱**（`ir_remote.known()` 看得到有哪些）。
規則是每次事件都重讀檔案，所以**改規則不用重啟服務**——
按一下開關就知道改對了沒。

## 去重：中樞會把同一次按鍵送好幾遍

實測與文件都提到中樞可能重送 report。同一組（sid, channel, action）
在 `DEDUPE_SEC` 內只執行一次，否則按一下風扇會開了又關（多數遙控器是 toggle）。

## ⚠ 尚未對真實硬體驗證

寫的時候中樞還沒插電。事件欄位名稱（`channel_0` / `button_0` / `dual_channel`）
因批次與韌體而異，所以這支**不預設欄位叫什麼**：規則檔寫什麼欄位就比對什麼欄位，
用 `aqara_discover.py` 看實際送出來的內容再填。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aqara_hub
import ir_remote

RULES_PATH = os.path.expanduser('~/switch_rules.json')
DEDUPE_SEC = 1.5

_last_fired: dict = {}


def load_rules() -> dict:
    """每次事件都重讀，改規則不用重啟服務。讀不到就回空規則（不要因此中斷）。"""
    try:
        with open(RULES_PATH, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        print(f'[bridge] 規則檔讀不了，這次先當成沒有規則: {exc}', flush=True)
        return {}


def _should_fire(sid: str, channel: str, action: str) -> bool:
    """去重：同一次按鍵中樞可能送好幾遍，短時間內只認第一次。"""
    key = (sid, channel, action)
    now = time.time()
    if now - _last_fired.get(key, 0.0) < DEDUPE_SEC:
        return False
    _last_fired[key] = now
    return True


def handle(msg: dict) -> None:
    if msg.get('cmd') not in ('report', 'heartbeat'):
        return
    sid = msg.get('sid')
    data = msg.get('data')
    if not sid or not isinstance(data, dict):
        return
    rules = load_rules().get(sid)
    if not rules:
        return

    for channel, actions in rules.items():
        value = data.get(channel)
        if value is None:
            continue
        code_name = actions.get(value) if isinstance(actions, dict) else None
        if not code_name:
            # 有動作但規則沒定義，印出來方便補規則
            print(f'[bridge] {sid} {channel}={value} 沒有對應規則', flush=True)
            continue
        if not _should_fire(sid, channel, value):
            print(f'[bridge] {sid} {channel}={value} 重複事件，略過', flush=True)
            continue
        try:
            reply = ir_remote.send(code_name)
            print(f'[bridge] {sid} {channel}={value} -> 發送紅外「{code_name}」: {reply}',
                  flush=True)
        except Exception as exc:                            # noqa: BLE001
            print(f'[bridge] 發送紅外「{code_name}」失敗: {exc!r}', flush=True)


def main() -> None:
    print('[bridge] 啟動，監聽 Aqara 中樞事件', flush=True)
    rules = load_rules()
    if rules:
        print(f'[bridge] 已載入 {len(rules)} 台裝置的規則: {list(rules)}', flush=True)
    else:
        print(f'[bridge] ⚠ {RULES_PATH} 不存在或沒有內容，'
              f'收到事件也不會做任何事。先跑 aqara_discover.py 查 sid', flush=True)

    hubs = aqara_hub.discover(timeout=6)
    if hubs:
        print(f"[bridge] 找到中樞: {[h.get('ip') for h in hubs]}", flush=True)
    else:
        print('[bridge] ⚠ whois 沒有中樞回應。仍會繼續監聽多播'
              '（有些韌體不回 whois 但照樣廣播事件）', flush=True)

    while True:
        try:
            aqara_hub.listen(handle)
        except KeyboardInterrupt:
            return
        except Exception as exc:                            # noqa: BLE001
            # 網路斷線、介面重啟都可能讓 socket 掛掉，睡一下重來，不要讓服務死掉
            print(f'[bridge] 監聽中斷，5 秒後重試: {exc!r}', flush=True)
            time.sleep(5)


if __name__ == '__main__':
    main()
