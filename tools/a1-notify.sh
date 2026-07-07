#!/usr/bin/env bash
# Cron watcher for the A1 launch retry loop (tools/launch-a1.sh) on media.
# Emails Matthew ONCE when the loop succeeds, or once if it stops without success.
# Creds file: ~/.a1-notify.env with EMAIL_HOST_USER= and EMAIL_HOST_PASSWORD=
# (pulled from the prod .env on oracle; gmail app password).
# Cron: */5 * * * * $HOME/hilobakestands/tools/a1-notify.sh >> $HOME/a1-notify-cron.log 2>&1
set -u
LOG="$HOME/a1-launch.log"
SENTINEL="$HOME/.a1-notify-sent"
CREDS="$HOME/.a1-notify.env"
TO="matt@giampapa.com"

[ -f "$SENTINEL" ] && exit 0          # already notified
[ -f "$LOG" ] || exit 0               # loop never started; nothing to report
[ -f "$CREDS" ] || { echo "ERROR: no creds file at $CREDS"; exit 1; }

if grep -q "SUCCESS - capacity secured" "$LOG"; then
  SUBJECT="[hilobakestands] A1 instance LAUNCHED"
  BODY="The A1 retry loop on media secured capacity.

Last log lines:
$(tail -8 "$LOG")

Next steps: rsync + bootstrap + move Cloudflare tunnel (see STATUS.md)."
elif ! pgrep -f 'launch-a1\.sh' >/dev/null; then
  SUBJECT="[hilobakestands] A1 retry loop STOPPED (no success)"
  BODY="launch-a1.sh is not running on media and the log has no success line.
It may have hit 5 consecutive unexpected errors, or the box rebooted.

Last log lines:
$(tail -12 "$LOG")"
else
  exit 0                              # still grinding; stay quiet
fi

export SUBJECT BODY TO
python3 - <<'PYEOF'
import os, smtplib, email.message

creds = {}
with open(os.path.expanduser('~/.a1-notify.env')) as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, _, v = line.partition('=')
            creds[k.strip()] = v.strip().strip('"').strip("'")

user, pw = creds['EMAIL_HOST_USER'], creds['EMAIL_HOST_PASSWORD']
msg = email.message.EmailMessage()
msg['From'] = f'Hilo Bake Stands <{user}>'
msg['To'] = os.environ['TO']
msg['Subject'] = os.environ['SUBJECT']
msg.set_content(os.environ['BODY'])
with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as s:
    s.starttls()
    s.login(user, pw)
    s.send_message(msg)
print('notification sent:', os.environ['SUBJECT'])
PYEOF
rc=$?
[ $rc -eq 0 ] && touch "$SENTINEL"    # only silence after a successful send
exit $rc
