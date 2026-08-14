"""端對端：組簽章正確的假 LINE webhook 打真正的服務，驗證風扇指令。

用真的 webhook 而不是 import 模組——另開 process import line_control 會去搶
GPIO，而且會有自己一份記憶體狀態，測不到實際服務的行為。
"""
import hashlib, hmac, base64, json, subprocess, time, urllib.request

cfg = json.load(open('/home/lpl1103/pi3_line_config.json'))
SECRET = cfg['channel_secret'].encode()


def send(text):
    body = json.dumps({'events': [{
        'type': 'message', 'replyToken': 'FAKE_TOKEN',
        'source': {'type': 'user', 'userId': 'Utest'},
        'message': {'type': 'text', 'id': '1', 'text': text},
    }]}, ensure_ascii=False).encode()
    sig = base64.b64encode(hmac.new(SECRET, body, hashlib.sha256).digest()).decode()
    since = subprocess.run(['date', '+%Y-%m-%d %H:%M:%S'],
                           capture_output=True, text=True).stdout.strip()
    time.sleep(1.1)
    req = urllib.request.Request('http://127.0.0.1:8000/callback', data=body,
                                 headers={'Content-Type': 'application/json',
                                          'X-Line-Signature': sig})
    urllib.request.urlopen(req, timeout=30).read()
    time.sleep(2.5)
    log = subprocess.run(['journalctl', '-u', 'line-control', '--since', since,
                          '--no-pager'], capture_output=True, text=True).stdout
    return log


print('對真正的服務送 LINE webhook，並確認機器人有回覆')
print('-' * 58)
for cmd in ['開風扇', '關風扇', '大風', '中風', '小風', '擺頭']:
    log = send(cmd)
    replied = '[line_reply]' in log
    print(f'  {cmd:6} -> {"有回覆" if replied else "沒有回覆 ⚠"}')
print()
print('注意：「有回覆」只代表指令被正確分派並送出紅外訊號，')
print('      不代表風扇真的收到——小黑豆還沒擺到風扇前面。')
