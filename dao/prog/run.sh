#!/bin/bash
cd /root/prog
file=../data
if [ -L "$file" ]
then
  echo "=> /root/prog/data exist"
else
  echo "=> /root/prog/data doesn't exist, made"
  ln -s /addons/day_ahead_dev/data $file
fi

cd /root/webserver/
file=app/static/data
if [ -L "$file" ]
then
  echo "=> /root/webserver/app/static/data exist"
else
  echo "=> /root/webserver/app/static/data doesn't exist, made"
  ln -s /addons/day_ahead_dev/data $file
fi
export PMIP_CBC_LIBRARY="/root/prog/miplib/lib/libCbc.so"
gunicorn --config gunicorn_config.py app:app &

cd /root/prog
bash ./watchdog.sh python3 day_ahead.py
#python3 day_ahead.py &





