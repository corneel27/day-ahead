#!/bin/bash
dir="/config/dao_data"
if [ ! -d "$dir" ]; then
  echo "=> directory dao_data made, files copied"
  cp -r /tmp/daodata /config/dao_data
  file=/config/dao_data/options.json
  if [ ! -L "$file" ]
    cp /config/dao_data/options_vb.json $file
  fi
  file=/config/dao_data/secrets.json
  if [ ! -L "$file" ]
    cp /config/dao_data/secrets_vb.json $file
  fi
else
  echo "=> directory dao_data exist"
fi

cd /root/dao/prog
file=../data
if [ -L "$file" ]
then
  echo "=> /root/dao/prog/data exist"
else
  echo "=> /root/dao/prog/data doesn't exist, made"
  ln -s /config/dao_data $file
fi

cd /root/dao/webserver/
file=app/static/data
if [ -L "$file" ]
then
  echo "=> /root/dao/webserver/app/static/data exist"
else
  echo "=> /root/dao/webserver/app/static/data doesn't exist, made"
  ln -s /config/dao_data $file
fi
export PMIP_CBC_LIBRARY="/root/dao/prog/miplib/lib/libCbc.so"
gunicorn --config gunicorn_config.py app:app &

cd /root/dao/prog
# bash ./watchdog.sh python3 day_ahead.py
# python3 day_ahead.py &
python3 loop.py






