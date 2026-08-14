#!/usr/bin/env python3
"""Aqara / 小米 中樞的「區域網路通訊協定」用戶端——只負責「聽」事件。

## 這支在整條鏈路的位置

    D1 無線開關 ──Zigbee──> Aqara 中樞 ──UDP 多播──> 這支 ──> ir_remote.py ──紅外──> 家電

Aqara 中樞跟博聯小黑豆是**兩個互不相通的生態系**（Aqara 走 Zigbee + 自家雲端，
博聯走 Wi-Fi + 自家雲端），Aqara App 裡沒有「控制博聯裝置」這個選項。
所以中間一定要有東西橋接，這支就是橋的左半邊。

## 協定長什麼樣

中樞開啟「區域網路通訊協定」後，會在區網做兩件事：

1. **回應探索**：往 `224.0.0.50:4321` 送 `{"cmd":"whois"}`，中樞會單播回
   `{"cmd":"iam","ip":...,"port":"9898","model":...,"sid":...}`
2. **多播事件**：子裝置有動作時，往 `224.0.0.50:9898` 廣播
   `{"cmd":"report","model":"...","sid":"...","data":"{...}"}`
   （注意 `data` 是**字串包著的 JSON**，要 parse 兩次）

## 為什麼只做「聽」不做「控制」

**讀事件不需要金鑰**，中樞是明文廣播的。要「控制」中樞上的裝置才需要 App 裡
那把 AES 金鑰。我們只需要知道「按鈕被按了」，所以完全不用碰金鑰——
少一個會過期、會被改動的依賴。

## ⚠ 這支還沒有對真實硬體驗證過

寫的時候中樞還沒插電。協定本身是公開且穩定的（小米閘道器 v2 時代就有），
但**不是每一款中樞都支援**：舊款（小米閘道器 v2、Aqara M1S/M2）有，
新款有些拿掉了。所以：

- 解析刻意寫得**寬鬆**：任何 JSON 都收、認不得的欄位就原樣記錄下來，
  不預設 D1 開關的 model 字串長怎樣（不同批次/韌體可能不同）
- 先用 `deploy/aqara_discover.py` 確認中樞找得到、事件收得到，
  再談後面的對應規則
"""
import json
import socket
import struct
import time

MULTICAST_GROUP = '224.0.0.50'
DISCOVER_PORT = 4321
EVENT_PORT = 9898


def discover(timeout: float = 6.0) -> list:
    """往多播位址問「誰在」，回傳中樞清單。

    回傳的每一筆是中樞原樣回的欄位，至少會有 ip / port / model / sid。
    找不到就回空清單——**這通常代表中樞沒開區網協定，而不是網路不通**。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(1.0)
    found = {}
    try:
        sock.sendto(json.dumps({'cmd': 'whois'}).encode(), (MULTICAST_GROUP, DISCOVER_PORT))
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            try:
                msg = json.loads(raw.decode('utf-8'))
            except (UnicodeDecodeError, ValueError):
                continue
            if msg.get('cmd') != 'iam':
                continue
            sid = msg.get('sid') or addr[0]
            msg.setdefault('ip', addr[0])
            found[sid] = msg
    finally:
        sock.close()
    return list(found.values())


def _parse(raw: bytes) -> dict | None:
    """把中樞送來的一包解析成 dict。

    `data` 欄位是字串包著的 JSON，要再 parse 一次；parse 失敗就原樣留著，
    不要因為一包格式沒見過就整個掛掉。
    """
    try:
        msg = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(msg, dict):
        return None
    data = msg.get('data')
    if isinstance(data, str):
        try:
            msg['data'] = json.loads(data)
        except ValueError:
            pass
    return msg


def listen(callback, stop=None, bind_addr: str = '0.0.0.0'):
    """加入多播群組，收到事件就呼叫 callback(msg)。

    `callback` 收到的是解析後的 dict。`stop` 傳一個 callable，回 True 就結束。
    這支會一直跑，例外只記錄不中斷——橋接程式不能因為一包壞掉的封包就死掉。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except (AttributeError, OSError):
        pass                       # 不是每個平台都有，沒有就算了
    sock.bind((bind_addr, EVENT_PORT))
    mreq = struct.pack('4sl', socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.settimeout(1.0)
    try:
        while True:
            if stop is not None and stop():
                return
            try:
                raw, _ = sock.recvfrom(8192)
            except socket.timeout:
                continue
            msg = _parse(raw)
            if msg is None:
                continue
            try:
                callback(msg)
            except Exception as exc:                       # noqa: BLE001
                print(f'[aqara_hub] callback 出錯（已忽略）: {exc!r}', flush=True)
    finally:
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
        except OSError:
            pass
        sock.close()


def describe(msg: dict) -> str:
    """把一包事件濃縮成一行方便讀的文字，設定與除錯時用。"""
    cmd = msg.get('cmd', '?')
    model = msg.get('model', '?')
    sid = msg.get('sid', '?')
    data = msg.get('data')
    if isinstance(data, dict):
        # 心跳包欄位很多且無趣，只留有變化的那些
        interesting = {k: v for k, v in data.items()
                       if k not in ('voltage', 'rgb', 'illumination')}
        body = json.dumps(interesting, ensure_ascii=False)
    else:
        body = str(data)
    return f'{cmd:9} {model:26} {sid:18} {body}'
