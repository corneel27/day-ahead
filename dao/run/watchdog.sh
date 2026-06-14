#!/usr/bin/env bash

WATCH_FILES=(
  "../data/options.json"
  "../data/secrets.json"
)

CMD=(python3 da_scheduler.py)

while true; do
    echo "Starting scheduler..."
    "${CMD[@]}" &
    PID=$!

    # Start inotifywait op de achtergrond
    inotifywait -q -e modify "${WATCH_FILES[@]}" &
    INOTIFY_PID=$!

    # Wacht tot OF scheduler stopt OF file wijziging plaatsvindt
    while true; do
        # Scheduler gecrasht / gestopt?
        if ! kill -0 "$PID" 2>/dev/null; then
            wait "$PID"
            EXIT=$?

            kill "$INOTIFY_PID" 2>/dev/null

            if [ "$EXIT" -eq 0 ]; then
                echo "Scheduler stopped normally"
            else
                logger "scheduler exited with $EXIT"
                echo "Scheduler crashed with exit code $EXIT"
                sleep 2
            fi

            break
        fi

        # Config gewijzigd?
        if ! kill -0 "$INOTIFY_PID" 2>/dev/null; then
            echo "Configuration changed, restarting scheduler..."
            kill "$PID" 2>/dev/null
            wait "$PID" 2>/dev/null
            break
        fi
        sleep 1
    done
done