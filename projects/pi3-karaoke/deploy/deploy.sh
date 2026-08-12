#!/usr/bin/env bash
# 把 src/ 底下的程式推到樹莓派並重啟服務。
#
#     deploy/deploy.sh                 # 推全部並重啟 line-control
#     deploy/deploy.sh line_control    # 只推一支
#     deploy/deploy.sh --check         # 只比對 repo 與樹莓派的差異，不推
#
# ⚠ 一定要用 mDNS 名稱不要寫死 IP。這個環境的網段換過（192.168.1.x → 192.168.0.x）、
#   Mac 主機名也換過，三次部署失敗都是這個原因。
#   ssh 出現 "Connection refused"（不是 timeout）通常代表那個 IP 已經被別台機器拿走。
set -euo pipefail

HOST="${PI_HOST:-lpl1103@raspberrypi.local}"
PORT="${PI_PORT:-8000}"
SRC="$(cd "$(dirname "$0")/../src" && pwd)"
MODULES=(line_control karaoke nlu stt voice_control radio_pool song_stats weather pi3_control ir_remote)

if [ "${1:-}" = "--check" ]; then
    TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
    for m in "${MODULES[@]}"; do
        scp -q "$HOST:~/$m.py" "$TMP/$m.py" 2>/dev/null || { printf '%-18s 樹莓派上沒有\n' "$m.py"; continue; }
        if diff -q "$SRC/$m.py" "$TMP/$m.py" >/dev/null; then printf '%-18s 一致\n' "$m.py"
        else printf '%-18s ⚠ 差 %s 行\n' "$m.py" "$(diff "$SRC/$m.py" "$TMP/$m.py" | grep -c '^[<>]')"; fi
    done
    exit 0
fi

TARGETS=("${MODULES[@]}")
[ $# -gt 0 ] && TARGETS=("$@")

for m in "${TARGETS[@]}"; do
    scp -q "$SRC/$m.py" "$HOST:~/$m.py"
    echo "推送 $m.py"
done

echo "重啟 line-control.service"
ssh "$HOST" 'sudo systemctl restart line-control.service && sleep 4 && systemctl is-active line-control.service'

# 只看狀態碼會被騙：ngrok 網域被 Mac 搶走時公開網址一樣回 200，內容卻是別的服務。
HOSTNAME_ONLY="${HOST#*@}"
CODE=$(curl -s -o /tmp/_deploy_check.html -w '%{http_code}' --max-time 15 "http://$HOSTNAME_ONLY:$PORT/karaoke" || echo 000)
if [ "$CODE" = "200" ] && grep -q '小樂點歌台' /tmp/_deploy_check.html; then
    echo "✅ /karaoke HTTP 200 且內容正確"
else
    echo "❌ /karaoke HTTP $CODE，或內容不是點歌台——檢查服務與 ngrok 網域歸屬"; exit 1
fi
