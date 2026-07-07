#!/usr/bin/env bash
# Retry-launch an Always-Free Ampere A1.Flex until capacity is available.
# v2: clock-skew (sleep/wake) errors are now retried instead of fatal;
#     unexpected errors retry up to 5x consecutively before stopping.
# Designed to run on an always-on Linux box (e.g. media) or a Mac.
set -uo pipefail
export SUPPRESS_LABEL_WARNING=True

COMPARTMENT="ocid1.tenancy.oc1..aaaaaaaaz6quvkkb57k5zkulphmyuifx3k5qxzplotnwghgg762nz27edjma"
AD="AFrf:US-SANJOSE-1-AD-1"
SHAPE="VM.Standard.A1.Flex"
DISPLAY_NAME="hilobakestands-a1"
SSH_KEY_FILE="${SSH_KEY_FILE:-$HOME/.ssh/id_ed25519.pub}"
SLEEP=90
BACKOFF_START=300
BACKOFF_MAX=1800
MAX_CONSECUTIVE_UNEXPECTED=5

[ -f "$SSH_KEY_FILE" ] || { echo "ERROR: SSH public key not found at $SSH_KEY_FILE — set SSH_KEY_FILE."; exit 1; }

echo "Resolving Ubuntu 24.04 image for $SHAPE ..."
IMAGE_ID=$(oci compute image list --compartment-id "$COMPARTMENT" \
  --operating-system "Canonical Ubuntu" --operating-system-version "24.04" \
  --shape "$SHAPE" --sort-by TIMECREATED --sort-order DESC \
  --query 'data[0].id' --raw-output 2>/dev/null)
echo "Resolving existing subnet ..."
SUBNET_ID=$(oci network subnet list --compartment-id "$COMPARTMENT" \
  --query 'data[0].id' --raw-output 2>/dev/null)
echo "Image:  $IMAGE_ID"
echo "Subnet: $SUBNET_ID"
[ -n "$IMAGE_ID" ] || { echo "ERROR: could not resolve image id"; exit 1; }
[ -n "$SUBNET_ID" ] || { echo "ERROR: could not resolve subnet id"; exit 1; }

echo "Starting retry loop (base ${SLEEP}s, 429-backoff ${BACKOFF_START}s). Ctrl-C to stop."
n=0
backoff=$BACKOFF_START
fails=0
while true; do
  n=$((n+1))
  ts=$(date '+%Y-%m-%d %H:%M:%S')
  out=$(oci compute instance launch \
    --availability-domain "$AD" \
    --compartment-id "$COMPARTMENT" \
    --shape "$SHAPE" \
    --shape-config '{"ocpus":1,"memoryInGBs":6}' \
    --image-id "$IMAGE_ID" \
    --subnet-id "$SUBNET_ID" \
    --assign-public-ip true \
    --display-name "$DISPLAY_NAME" \
    --ssh-authorized-keys-file "$SSH_KEY_FILE" 2>&1)
  rc=$?
  jitter=$(( RANDOM % 20 ))
  if [ $rc -eq 0 ]; then
    echo "[$ts] attempt $n: SUCCESS - capacity secured, instance is provisioning."
    echo "$out" | grep -E '"id"|"display-name"|lifecycle-state' | head -5
    osascript -e 'display notification "A1 instance launched!" with title "Oracle A1"' 2>/dev/null
    printf '\a'
    break
  elif echo "$out" | grep -qi 'TooManyRequests'; then
    fails=0
    echo "[$ts] attempt $n: throttled (429), backing off $((backoff+jitter))s"
    sleep $((backoff + jitter))
    backoff=$(( backoff * 2 )); [ "$backoff" -gt "$BACKOFF_MAX" ] && backoff=$BACKOFF_MAX
  elif echo "$out" | grep -qi 'capacity'; then
    fails=0
    backoff=$BACKOFF_START
    echo "[$ts] attempt $n: out of capacity, retrying in $((SLEEP+jitter))s"
    sleep $((SLEEP + jitter))
  elif echo "$out" | grep -qiE 'clock skew|NotAuthenticated'; then
    # Happens after laptop sleep/wake: request signed pre-sleep, sent post-wake.
    # A fresh attempt signs a fresh timestamp, so retry quickly.
    fails=0
    backoff=$BACKOFF_START
    echo "[$ts] attempt $n: clock skew (sleep/wake), retrying in 15s"
    sleep 15
  elif echo "$out" | grep -qiE 'timed out|timeout|RequestException|could not connect|connection|max retries|name or service|temporarily|"status": *5'; then
    fails=0
    backoff=$BACKOFF_START
    echo "[$ts] attempt $n: transient network/service error, retrying in $((SLEEP+jitter))s"
    sleep $((SLEEP + jitter))
  else
    fails=$((fails+1))
    echo "[$ts] attempt $n: unexpected error ($fails/$MAX_CONSECUTIVE_UNEXPECTED consecutive):"
    echo "$out" | head -20
    if [ "$fails" -ge "$MAX_CONSECUTIVE_UNEXPECTED" ]; then
      echo "Too many consecutive unexpected errors, stopping."
      break
    fi
    sleep $((SLEEP + jitter))
  fi
done
