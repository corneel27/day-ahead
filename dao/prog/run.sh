#!/bin/bash
dir="/addon_config/daodata"
if [ ! -d "$dir" ]; then
  cp -r /tmp/daodata /addon_config
  cp /addon_config/daodata/options_vb.json /addon_config/daodata/options.json
  cp /addon_config/daodata/secrets_vb.json /addon_config/daodata/secrets.json
fi

cd /root/dao/prog
file=../data
if [ -L "$file" ]
then
  echo "=> /root/dao/prog/data exist"
else
  echo "=> /root/dao/prog/data doesn't exist, made"
  ln -s /addon_config/daodata $file
fi

cd /root/dao/webserver/
file=app/static/data
if [ -L "$file" ]
then
  echo "=> /root/dao/webserver/app/static/data exist"
else
  echo "=> /root/dao/webserver/app/static/data doesn't exist, made"
  ln -s /addon_config/daodata $file
fi
export PMIP_CBC_LIBRARY="/root/dao/prog/miplib/lib/libCbc.so"
gunicorn --config gunicorn_config.py app:app &

cd /root/dao/prog
# bash ./watchdog.sh python3 day_ahead.py
# python3 day_ahead.py &





