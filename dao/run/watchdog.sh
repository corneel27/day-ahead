#!/bin/sh

# Heartbeat file
HEARTBEAT="/tmp/dao_scheduler_heartbeat"

# Stale-heartbeat threshold: watchdog restarts the scheduler when the heartbeat file is
# older than MAX_HEARTBEAT_AGE_S seconds (checked every CHECK_INTERVAL_S). Must be >= longest inline
# scheduler task; inline runs do not refresh the heartbeat until they finish. Subprocess
# actions refresh it in a poll loop. Higher heartbeat_age = more tolerance for long inline work but slower hang recovery.
MAX_HEARTBEAT_AGE_S=450

# How often the loop checks child, inotify, and heartbeat age.
# Users expect config changes to apply immediately; polling every 2s keeps reload latency low
CHECK_INTERVAL_S=2

start_child() {
  # Drop stale heartbeat from a previous run so we don't restart-loop before the child writes.
  rm -f "$HEARTBEAT"
  "$@" &
  CHILD_PID=$!
  echo "watchdog: started da_scheduler pid=$CHILD_PID cmd=$*"
}

stop_child() {
  if [ -n "$CHILD_PID" ] && kill -0 "$CHILD_PID" 2>/dev/null; then
    echo "watchdog: stopping da_scheduler pid=$CHILD_PID"
    kill "$CHILD_PID" || true
    sleep 2
    if kill -0 "$CHILD_PID" 2>/dev/null; then
      echo "watchdog: da_scheduler still alive -> SIGKILL pid=$CHILD_PID"
      kill -9 "$CHILD_PID" || true
    fi
  fi
}

start_inotify() {
  inotifywait "../data/options.json" "../data/secrets.json" -e modify &
  INOTIFY_PID=$!
}

start_child "$@"
start_inotify

while true; do
  # 1) Child exited/crashed -> restart
  if ! kill -0 "$CHILD_PID" 2>/dev/null; then
    echo "watchdog: da_scheduler exited -> restart"
    start_child "$@"
  fi

  # 2) Config modified -> restart child (inotify exits after first modify event)
  if ! kill -0 "$INOTIFY_PID" 2>/dev/null; then
    echo "watchdog: config modified -> restart da_scheduler"
    stop_child
    start_child "$@"
    start_inotify
  fi

  # 3) Heartbeat stale -> restart child
  if [ -f "$HEARTBEAT" ]; then
    now=$(date +%s)
    hb=$(cat "$HEARTBEAT" 2>/dev/null || echo 0)
    hb_int=$(echo "$hb" | cut -d. -f1)
    age=$((now - hb_int))
    if [ "$age" -gt "$MAX_HEARTBEAT_AGE_S" ]; then
      echo "watchdog: heartbeat stale age=${age}s -> restart da_scheduler"
      stop_child
      start_child "$@"
    fi
  fi

  # Ensure an inotify watcher is running
  if [ -z "$INOTIFY_PID" ] || ! kill -0 "$INOTIFY_PID" 2>/dev/null; then
    start_inotify
  fi

  sleep "$CHECK_INTERVAL_S"
done
