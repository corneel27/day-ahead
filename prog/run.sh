#!/bin/bash
cd /root/prog
file=../data
if [ -L "$file" ]
then
  echo "=> data exist"
else
  echo "=> data doesn't exist"
  ln -s /addons/test_da/data $file
fi

bash ./watchdog.sh python3 day_ahead.py 
python3 da_webserver.py &


