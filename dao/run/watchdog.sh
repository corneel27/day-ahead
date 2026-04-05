#!/bin/sh
while true; do
  $@ &
  PID=$!
  inotifywait "../data/options.json" "../data/secrets.json" -e modify
  kill $PID
done

