#!/bin/sh
while true; do
  $@ &
  PID=$!
  inotifywait "../data/" -e modify
  kill $PID
done

