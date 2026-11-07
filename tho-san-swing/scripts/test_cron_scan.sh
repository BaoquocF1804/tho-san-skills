#!/usr/bin/env bash
# Self-check for cron_scan.sh with a fake scan and a fake hermes: no network, no real Telegram.
#   bash test_cron_scan.sh
set -u
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
export SWING_STATE="$T/state" HERMES="$T/hermes" SCAN="$T/scan"
mkdir -p "$SWING_STATE"
cat > "$HERMES" <<EOF
#!/usr/bin/env bash
f=""; while [ \$# -gt 0 ]; do [ "\$1" = "--file" ] && f="\$2"; shift; done
[ -e "$T/hermes_down" ] && exit 1
echo "\$f" >> "$T/sent"
EOF
cat > "$SCAN" <<EOF
#!/usr/bin/env bash
[ -e "$T/scan_down" ] && { echo "boom: Yahoo unavailable"; exit 1; }
echo "report" > "$SWING_STATE/tg-20261109.md"
if [ -e "$T/scanned" ]; then echo "Chưa có phiên mới đóng cửa kể từ lần quét trước"; else touch "$T/scanned"; fi
echo "TG_FILE: $SWING_STATE/tg-20261109.md (6 ký tự)"
EOF
chmod +x "$HERMES" "$SCAN"
run() { /bin/bash "$HERE/cron_scan.sh" > /dev/null 2>&1; }
fail() { echo "FAIL: $1"; exit 1; }
sent() { if [ -f "$T/sent" ]; then grep -c "$1" "$T/sent"; else echo 0; fi; }

touch "$T/scan_down" "$T/hermes_down"
run; run
[ "$(sent alert)" = 0 ] && ! grep -q alert "$SWING_STATE/tg_pending" 2>/dev/null || fail "alert before 3 failures"
run                                           # 3rd failure: alert, but hermes is down -> queued
grep -q alert "$SWING_STATE/tg_pending" || fail "alert not queued while hermes is down"
rm "$T/hermes_down"; run                      # 4th failure: queued alert resent, no new alert
[ "$(sent alert)" = 1 ] || fail "queued alert not resent exactly once"
for _ in $(seq 5 24); do run; done            # 24th failure: daily reminder
[ "$(sent alert)" = 2 ] || fail "no reminder at 24 failures"
rm "$T/scan_down"; touch "$T/hermes_down"; run   # scan works, the report fails to send -> queued
[ "$(cat "$SWING_STATE/scan_fails")" = 0 ] || fail "failure streak not reset"
grep -q tg-20261109 "$SWING_STATE/tg_pending" || fail "report not queued"
rm "$T/hermes_down"; run                      # no new session: only the queued report goes out
[ "$(sent tg-20261109)" = 1 ] || fail "report not resent exactly once"
[ -s "$SWING_STATE/tg_pending" ] && fail "queue not emptied"
echo "cron_scan selftest ok"
