#!/bin/sh

HEARTBEAT="/tmp/dao_scheduler_heartbeat"
# Scheduler updates heartbeat every ~5s while tasks run; 120s leaves enough slack.
MAX_HEARTBEAT_AGE_S=120
# Users expect config changes to apply immediately; polling every 1s keeps reload latency low
CHECK_INTERVAL_S=1

start_child() {
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

