#!/usr/bin/env bash

WATCH_FILES=(
    "/root/dao/data/options.json"
    "/root/dao/data/secrets.json"
)

SCHEDULER_PID=""
GUNICORN_PID=""
INOTIFY_PID=""

start_processes() {
    echo "Starting scheduler..."
    (
        cd /root/dao/prog || exit 1
        exec python3 da_scheduler.py
    ) &
    SCHEDULER_PID=$!

    echo "Starting gunicorn..."
    (
        cd /root/dao/webserver || exit 1
        exec gunicorn --config gunicorn_config.py app:app
    ) &
    GUNICORN_PID=$!

    echo "Scheduler PID: $SCHEDULER_PID"
    echo "Gunicorn PID:  $GUNICORN_PID"
}

stop_scheduler() {
    if [ -n "$SCHEDULER_PID" ] && kill -0 "$SCHEDULER_PID" 2>/dev/null; then
        echo "Stopping scheduler..."
        kill -TERM "$SCHEDULER_PID" 2>/dev/null
        wait "$SCHEDULER_PID" 2>/dev/null
    fi
}

stop_gunicorn() {
    if [ -n "$GUNICORN_PID" ] && kill -0 "$GUNICORN_PID" 2>/dev/null; then
        echo "Stopping gunicorn..."
        kill -TERM "$GUNICORN_PID" 2>/dev/null
        wait "$GUNICORN_PID" 2>/dev/null
    fi
}

cleanup() {
    echo "Watchdog stopping..."

    if [ -n "$INOTIFY_PID" ] && kill -0 "$INOTIFY_PID" 2>/dev/null; then
        kill "$INOTIFY_PID" 2>/dev/null
    fi

    stop_scheduler
    stop_gunicorn

    exit 0
}

trap cleanup SIGTERM SIGINT

while true; do

    start_processes

    # Wacht op een configuratiewijziging.
    # close_write: bestand is volledig geschreven en gesloten
    # move: bestand is vervangen door een ander bestand

    inotifywait -q -e close_write,move "${WATCH_FILES[@]}" &
    INOTIFY_PID=$!

    while true; do

        # ------------------------------------------------------------
        # Scheduler is gestopt/gecrasht
        # ------------------------------------------------------------
        if ! kill -0 "$SCHEDULER_PID" 2>/dev/null; then
            wait "$SCHEDULER_PID" 2>/dev/null
            EXIT=$?

            kill "$INOTIFY_PID" 2>/dev/null

            if [ "$EXIT" -eq 0 ]; then
                echo "scheduler stopped normally"
            else
                echo "scheduler crashed with exit code $EXIT"
                sleep 2
            fi

            # Gunicorn ook stoppen; daarna worden beide opnieuw gestart.
            stop_gunicorn

            break
        fi

        # ------------------------------------------------------------
        # Gunicorn is gestopt/gecrasht
        # ------------------------------------------------------------
        if ! kill -0 "$GUNICORN_PID" 2>/dev/null; then
            wait "$GUNICORN_PID" 2>/dev/null
            EXIT=$?

            kill "$INOTIFY_PID" 2>/dev/null

            if [ "$EXIT" -eq 0 ]; then
                echo "gunicorn stopped normally"
            else
                echo "gunicorn crashed with exit code $EXIT"
                sleep 2
            fi

            # Scheduler ook stoppen; daarna worden beide opnieuw gestart.
            stop_scheduler

            break
        fi

        # ------------------------------------------------------------
        # Configuratie gewijzigd
        # ------------------------------------------------------------
        if ! kill -0 "$INOTIFY_PID" 2>/dev/null; then
            echo "Configuration changed, restarting scheduler and reloading gunicorn..."

            kill "$INOTIFY_PID" 2>/dev/null

            # Scheduler volledig opnieuw starten.
            stop_scheduler

            # Gunicorn master een HUP geven.
            #
            # Gunicorn blijft draaien, maar start zijn workers
            # opnieuw. Daardoor wordt DaBase opnieuw geïnitialiseerd
            # en wordt de nieuwe configuratie geladen.
            if kill -0 "$GUNICORN_PID" 2>/dev/null; then
                echo "Reloading gunicorn..."
                kill -HUP "$GUNICORN_PID" 2>/dev/null
            fi

            break
        fi

        sleep 1
    done

done
