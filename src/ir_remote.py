#!/usr/bin/env python3
"""用博聯（Broadlink）小黑豆發紅外線，遙控風扇等家電。

## 為什麼走區網直連，不走雲端

`python-broadlink` 可以在**同一個區網內直接跟裝置對話**，不需要博聯的雲端服務、
不需要帳號密碼、不會因為對方 API 改版就壞掉，延遲也只有幾十毫秒。

代價是**紅外線碼要自己學一次**：手機 App 裡的碼存在博聯雲端，我們拿不到。
做法是讓小黑豆進入學習模式，人拿實體遙控器對著它按一下，把訊號存下來。
學一次就永久有效（存成 JSON）。

## 為什麼碼要存檔而不是每次都學

紅外線碼就是一串固定的時序資料，學到之後可以無限重放。
存成 `~/ir_codes.json`，重開機也還在。

## 風扇的開關通常是同一顆鍵

多數電風扇的遙控器只有一顆電源鍵，按一下開、再按一下關（toggle），
沒有獨立的「開」跟「關」。所以 `開風扇` 跟 `關風扇` 送的是同一個碼，
實際結果取決於風扇目前的狀態——**這是遙控器本身的限制，不是程式沒做好**。
"""
import json
import os
import time

CODES_PATH = os.path.expanduser('~/ir_codes.json')
DISCOVER_TIMEOUT = 6
LEARN_TIMEOUT = 25


def _load_codes():
    try:
        with open(CODES_PATH, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_codes(codes):
    with open(CODES_PATH, 'w', encoding='utf-8') as f:
        json.dump(codes, f, ensure_ascii=False, indent=2)


def discover(timeout=DISCOVER_TIMEOUT):
    """找出區網裡的博聯裝置。回傳 [(型號, IP, MAC, device 物件)]。"""
    try:
        import broadlink
    except ImportError:
        return []
    try:
        devices = broadlink.discover(timeout=timeout)
    except Exception:
        return []
    out = []
    for d in devices:
        try:
            d.auth()
        except Exception:
            continue
        model = getattr(d, 'model', None) or type(d).__name__
        out.append((model, d.host[0], ''.join(f'{b:02x}' for b in d.mac[::-1]), d))
    return out


_cached_device = None


def _device(force_rediscover: bool = False):
    """拿一台可用的裝置。找不到回 None。

    ## 為什麼要快取

    原本每次發送都重新廣播探索一次，那是 6 秒的 UDP timeout——
    使用者在 LINE 傳「關風扇」要等 6 秒才有反應，連續送多個指令更是難用。
    快取住 device 物件之後，第二次以後的發送幾乎是即時的。

    ## 但 IP 會變，所以不能只快取

    小黑豆的 IP 由 DHCP 配發。快取住之後如果 IP 變了，送出去會失敗——
    所以 `send()` 在發送失敗時會帶 `force_rediscover=True` 再試一次，
    等於「先用快的，壞了才走慢的」。這樣兼顧速度與正確性。
    """
    global _cached_device
    if _cached_device is not None and not force_rediscover:
        return _cached_device
    devs = discover()
    _cached_device = devs[0][3] if devs else None
    return _cached_device


def learn(name, timeout=LEARN_TIMEOUT):
    """進入學習模式，等人按遙控器。學到就存起來。

    回傳 (成功?, 訊息)。**這一步一定需要人在現場按遙控器**，沒有辦法自動化。
    """
    dev = _device()
    if dev is None:
        return False, '區網裡找不到博聯裝置。確認小黑豆有通電、跟樹莓派在同一個網段。'
    try:
        dev.enter_learning()
    except Exception as e:
        return False, f'無法進入學習模式：{e!r}'

    deadline = time.time() + timeout
    packet = None
    while time.time() < deadline:
        time.sleep(1)
        try:
            packet = dev.check_data()
        except Exception:
            packet = None
        if packet:
            break
    if not packet:
        return False, f'{timeout} 秒內沒收到紅外線訊號。請把遙控器對準小黑豆再按一次。'

    codes = _load_codes()
    codes[name] = packet.hex()
    _save_codes(codes)
    return True, f'已學會「{name}」，之後可以直接用。'


def send(name, label=None):
    """發送已學會的碼。回傳給使用者看的訊息。"""
    label = label or name
    codes = _load_codes()
    if name not in codes:
        return (f'還沒有學過「{label}」的紅外線碼。\n'
                f'請在樹莓派上執行：python3 ir_remote.py learn {name}\n'
                f'然後把遙控器對準小黑豆按一下對應的按鍵。')
    payload = bytes.fromhex(codes[name])
    # 先用快取的裝置；失敗才重新探索再試一次（IP 可能被 DHCP 換掉了）
    for attempt in (False, True):
        dev = _device(force_rediscover=attempt)
        if dev is None:
            if attempt:
                return '區網裡找不到博聯裝置（小黑豆）。確認它有通電、且跟樹莓派同網段。'
            continue
        try:
            dev.send_data(payload)
            return f'📡 已送出「{label}」訊號'
        except Exception as e:
            if attempt:
                return f'發送失敗：{e!r}'
    return '區網裡找不到博聯裝置（小黑豆）。確認它有通電、且跟樹莓派同網段。'


def known():
    return sorted(_load_codes())


if __name__ == '__main__':
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'discover'
    if cmd == 'discover':
        devs = discover()
        if not devs:
            print('找不到博聯裝置。檢查：小黑豆有通電？跟這台機器同一個網段？')
        for model, ip, mac, _ in devs:
            print(f'  {model}  {ip}  {mac}')
    elif cmd == 'learn':
        name = sys.argv[2] if len(sys.argv) > 2 else 'fan_power'
        print(f'準備學習「{name}」——請把遙控器對準小黑豆，按下對應按鍵…')
        ok, msg = learn(name)
        print(('✅ ' if ok else '❌ ') + msg)
    elif cmd == 'send':
        print(send(sys.argv[2] if len(sys.argv) > 2 else 'fan_power'))
    elif cmd == 'list':
        print('已學會的碼:', known() or '(還沒有)')
