#!/usr/bin/env python3
"""Aqara 中樞的設定／診斷工具——插電之後第一支要跑的東西。

    python3 aqara_discover.py            # 探索中樞 + 即時印出所有事件
    python3 aqara_discover.py --scan     # 只探索，不監聽
    python3 aqara_discover.py --raw      # 連心跳包也印（很吵，除錯用）

## 為什麼需要這支

D1 開關的 model 字串、按鍵欄位名稱，會因為批次與韌體而不同
（`channel_0` / `button_0` / `dual_channel` 都出現過）。與其憑猜測寫死，
**不如讓實際的裝置自己告訴我們**：跑起來、按幾下按鈕、把印出來的東西記下來，
再據此寫對應規則。

## 看不到中樞的話

依序確認：

1. 中樞跟樹莓派在**同一個網段**（多播不跨網段。2.4G/5G 若被隔離也會失敗）
2. Aqara App → 中樞 → 設定 → **開啟「區域網路通訊協定」**（有些韌體叫「開發者模式」）
3. 中樞型號有沒有支援。舊款（小米閘道器 v2、Aqara M1S/M2）有；**新款有些拿掉了**
   ——沒有的話這條路走不通，要改用 Zigbee 接收器直接收 D1，或改走 Home Assistant
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
sys.path.insert(0, os.path.expanduser('~'))          # 樹莓派上程式是平鋪在家目錄

import aqara_hub                                      # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scan', action='store_true', help='只探索中樞，不監聽事件')
    ap.add_argument('--raw', action='store_true', help='連心跳包也印出來')
    ap.add_argument('--timeout', type=float, default=8.0)
    args = ap.parse_args()

    print('正在探索中樞…（往 224.0.0.50:4321 送 whois）')
    hubs = aqara_hub.discover(timeout=args.timeout)
    if not hubs:
        print()
        print('❌ 找不到中樞。依序檢查：')
        print('   1. 中樞跟樹莓派在同一個網段？（多播不跨網段）')
        print('   2. Aqara App 裡開啟「區域網路通訊協定」了嗎？')
        print('   3. 這款中樞有沒有支援？新款有些拿掉了')
        print()
        print('   注意：即使中樞沒回應 whois，事件多播有時仍收得到。')
        print('   可以直接跑不帶 --scan 的模式，按按鈕看看有沒有東西進來。')
    else:
        print(f'\n✅ 找到 {len(hubs)} 台中樞：\n')
        for h in hubs:
            print(f"   ip    {h.get('ip')}")
            print(f"   sid   {h.get('sid')}      <- 中樞的識別碼")
            print(f"   model {h.get('model')}     <- 型號，決定支援程度")
            print(f"   port  {h.get('port')}")
            print()

    if args.scan:
        return

    print('=' * 74)
    print('開始監聽事件。現在請「按幾下 D1 開關」——左鍵、右鍵、雙擊、長按各試一次。')
    print('把下面印出來的 model 與 sid 記下來，那就是寫對應規則要用的東西。')
    print('（Ctrl+C 結束）')
    print('=' * 74)
    print(f"{'時間':8} {'cmd':9} {'model':26} {'sid':18} data")
    print('-' * 74)

    seen = {}

    def on_event(msg):
        cmd = msg.get('cmd', '')
        # 心跳包每分鐘都有、內容沒變化，預設濾掉才看得到按鈕事件
        if not args.raw and cmd == 'heartbeat':
            return
        print(f"{time.strftime('%H:%M:%S')} {aqara_hub.describe(msg)}", flush=True)
        key = (msg.get('model'), msg.get('sid'))
        if key[1]:
            seen[key] = seen.get(key, 0) + 1

    try:
        aqara_hub.listen(on_event)
    except KeyboardInterrupt:
        pass
    finally:
        if seen:
            print('\n' + '=' * 74)
            print('這次收到的裝置（把要用的那台的 model 與 sid 記下來）：')
            for (model, sid), n in sorted(seen.items(), key=lambda kv: -kv[1]):
                print(f'   {model:26} {sid:18} 收到 {n} 次')
        else:
            print('\n（這段時間沒收到任何事件）')


if __name__ == '__main__':
    main()
