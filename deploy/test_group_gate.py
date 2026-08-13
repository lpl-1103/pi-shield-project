"""對真正在跑的服務送簽章正確的假 webhook，驗證群組閘門。

用「排隊」當測試指令（唯讀，無副作用）。
判斷「有沒有回覆」的方式：line_reply 用假的 replyToken 打 LINE API 會拿到 4xx，
程式會 print 一行 [line_reply]，到 journal 裡撈得到。
"""
import hashlib, hmac, base64, json, subprocess, time, urllib.request

cfg = json.load(open('/home/lpl1103/pi3_line_config.json'))
SECRET = cfg['channel_secret'].encode()
URL = 'http://127.0.0.1:8000/callback'


def send(text, source_type, mention=None, label=''):
    msg = {'type': 'text', 'id': '1', 'text': text}
    if mention:
        msg['mention'] = mention
    body = json.dumps({'events': [{
        'type': 'message', 'replyToken': 'FAKE_TOKEN_FOR_TEST',
        'source': {'type': source_type, 'userId': 'Utest',
                   **({'groupId': 'Gtest'} if source_type == 'group' else {})},
        'message': msg,
    }]}, ensure_ascii=False).encode()
    sig = base64.b64encode(hmac.new(SECRET, body, hashlib.sha256).digest()).decode()
    since = subprocess.run(['date', '+%Y-%m-%d %H:%M:%S'], capture_output=True, text=True).stdout.strip()
    time.sleep(1.1)
    req = urllib.request.Request(URL, data=body,
                                 headers={'Content-Type': 'application/json',
                                          'X-Line-Signature': sig})
    urllib.request.urlopen(req, timeout=20).read()
    time.sleep(2.5)
    log = subprocess.run(['journalctl', '-u', 'line-control', '--since', since, '--no-pager'],
                         capture_output=True, text=True).stdout
    return '[line_reply]' in log


TESTS = [
    ('群組・無喚醒詞',        '排隊',            'group', None,                                        False),
    ('群組・有喚醒詞',        '小樂 排隊',        'group', None,                                        True),
    ('群組・@全體成員',       '@All 排隊',       'group', {'mentionees': [{'type': 'all'}]},           False),
    ('群組・@某人',           '@小明 排隊',       'group', None,                                        False),
    ('群組・單字元(燈泡)',     '1',              'group', None,                                        False),
    ('群組・閒聊',            '今天要吃什麼',      'group', None,                                        False),
    ('一對一・直接下指令',     '排隊',            'user',  None,                                        True),
    ('一對一・@全體成員',      '@All 排隊',       'user',  {'mentionees': [{'type': 'all'}]},           False),
]

print(f"{'情境':<20} {'訊息':<16} {'預期':<6} {'實際':<6} 結果")
print('-' * 62)
bad = 0
for label, text, src, mention, expect_reply in TESTS:
    got = send(text, src, mention, label)
    ok = got == expect_reply
    bad += 0 if ok else 1
    e = '會回' if expect_reply else '不回'
    g = '會回' if got else '不回'
    print(f"{label:<20} {text:<16} {e:<6} {g:<6} {'OK' if ok else 'FAIL'}")
print()
print('全部通過' if bad == 0 else f'{bad} 項失敗')
