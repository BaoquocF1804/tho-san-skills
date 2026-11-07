#!/usr/bin/env bash
# Hourly cron job for the swing paper hunter. `scan` acts once per finished US session (it is idempotent),
# so this sends Telegram only when a new session was processed and stays quiet otherwise.
# - 3 failed scans in a row send one alert, repeated every 24 failures (about once a day of hourly runs).
# - A Telegram message that fails to send is queued and sent again at the start of the next run.
#   crontab: 7 * * * * flock -n /tmp/tho-san-swing.lock /bin/bash <this file>
# SWING_STATE, SCAN and HERMES can be overridden (the self-check uses fakes).
set -u
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
STATE="${SWING_STATE:-$HOME/.local/share/tho-san-swing}"
SCAN="${SCAN:-/usr/bin/python3 $DIR/swing_paper.py scan}"
HERMES="${HERMES:-$HOME/.local/bin/hermes}"
LOG="$STATE/cron.log"
PENDING="$STATE/tg_pending"   # files still to send, one path per line
FAILS="$STATE/scan_fails"     # failed scans in a row
mkdir -p "$STATE"
stamp() { date '+%F %T'; }

send() {  # send one file; on failure queue it for the next run
    if "$HERMES" send --to telegram --file "$1" >> "$LOG" 2>&1; then
        return 0
    fi
    grep -qxF "$1" "$PENDING" 2>/dev/null || echo "$1" >> "$PENDING"
    return 1
}

if [ -s "$PENDING" ]; then  # retry what failed before, oldest first
    left=""
    while IFS= read -r f; do
        [ -f "$f" ] || continue
        if "$HERMES" send --to telegram --file "$f" >> "$LOG" 2>&1; then
            echo "$(stamp) resent $f" >> "$LOG"
        else
            left="$left$f"$'\n'
        fi
    done < "$PENDING"
    printf '%s' "$left" > "$PENDING"
fi

if ! OUT="$($SCAN 2>&1)"; then
    n=$(( $(cat "$FAILS" 2>/dev/null || echo 0) + 1 ))
    echo "$n" > "$FAILS"
    echo "$(stamp) scan failed ($n in a row): $(echo "$OUT" | tail -3 | tr '\n' ' ')" >> "$LOG"
    if [ "$n" -eq 3 ] || [ $(( n % 24 )) -eq 0 ]; then
        ALERT="$STATE/alert-$(date +%Y%m%d%H%M).md"
        printf '⚠️ Thợ săn Swing (giấy): quét lỗi %s lần liền, lần cuối lúc %s.\nLỗi: %s\nSổ giấy chưa được cập nhật; script tự thử lại mỗi giờ. Log: %s\n' \
            "$n" "$(date '+%H:%M %d/%m')" "$(echo "$OUT" | tail -1)" "$LOG" > "$ALERT"
        send "$ALERT" && echo "$(stamp) failure alert sent" >> "$LOG" || echo "$(stamp) failure alert queued" >> "$LOG"
    fi
    exit 1
fi
echo 0 > "$FAILS"
case "$OUT" in
    *"Chưa có phiên mới"*) echo "$(stamp) no new session" >> "$LOG"; exit 0 ;;
esac
TG="$(echo "$OUT" | sed -n 's/^TG_FILE: \([^ ]*\).*/\1/p')"
DAY="$(basename "$TG" .md)"
if send "$TG"; then  # the file's first line is the title
    echo "$(stamp) session ${DAY#tg-} processed, Telegram sent" >> "$LOG"
else
    echo "$(stamp) session ${DAY#tg-} processed, Telegram failed: queued for the next run" >> "$LOG"
fi
