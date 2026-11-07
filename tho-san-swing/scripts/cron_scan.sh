#!/usr/bin/env bash
# Hourly cron job for the swing paper hunter. `scan` acts once per finished US session (it is idempotent),
# so this sends Telegram only when a new session was processed and stays quiet otherwise.
#   crontab: 7 * * * * flock -n /tmp/tho-san-swing.lock /bin/bash <this file>
set -u
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
LOG="$HOME/.local/share/tho-san-swing/cron.log"
mkdir -p "$(dirname "$LOG")"
stamp() { date '+%F %T'; }

if ! OUT="$(/usr/bin/python3 "$DIR/swing_paper.py" scan 2>&1)"; then
    echo "$(stamp) scan failed: $(echo "$OUT" | tail -3 | tr '\n' ' ')" >> "$LOG"
    exit 1
fi
case "$OUT" in
    *"Chưa có phiên mới"*) echo "$(stamp) no new session" >> "$LOG"; exit 0 ;;
esac
TG="$(echo "$OUT" | sed -n 's/^TG_FILE: \([^ ]*\).*/\1/p')"
DAY="$(basename "$TG" .md)"        # tg-YYYYMMDD
DAY="${DAY#tg-}"
if "$HOME/.local/bin/hermes" send --to telegram --file "$TG" >> "$LOG" 2>&1; then  # the file's first line is the title
    echo "$(stamp) session ${DAY} processed, Telegram sent" >> "$LOG"
else
    echo "$(stamp) session ${DAY} processed, hermes send FAILED" >> "$LOG"
fi
