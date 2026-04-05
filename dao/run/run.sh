#!/command/with-contenv bashio
# exit immediately if a command exits with a non-zero status
set -e

dir="/config/dao_data"
if [ ! -d "$dir" ]; then
  bashio::log.info "=> directory dao_data made, files copied"
  cp -r /tmp/daodata /config/dao_data
  file=/config/dao_data/options.json
  if [ ! -L "$file" ]; then
    cp /config/dao_data/options_start.json $file
  fi
  file=/config/dao_data/secrets.json
  if [ ! -L "$file" ]; then
    cp /config/dao_data/secrets_vb.json $file
  fi
else
  bashio::log.info "=> directory dao_data exist"
fi

cd /root/dao/prog
file=../data
if [ -L "$file" ]
then
  bashio::log.info "=> /root/dao/data exist"
else
  bashio::log.info "=> /root/dao/data doesn't exist, made"
  ln -s /config/dao_data $file
fi

cd /root/dao/webserver/
file=app/static/data
if [ -L "$file" ]
then
  bashio::log.info "=> /root/dao/webserver/app/static/data exist"
else
  bashio::log.info "=> /root/dao/webserver/app/static/data doesn't exist, made"
  ln -s /config/dao_data $file
fi

export PYTHONPATH="/root:/root/dao:/root/dao/lib:/root/dao/prog"
cd /root/dao/prog
python3 check_db.py || { bashio::log.info "check_db.py failed, exiting"; sleep 5; exit 1; }

if [bashio::config.true 'use_self_compiled_miplib'; then
  if [ -d /config/miplib/lib ]; then
    bashio::log.info "Copying saved miplib-binaries"
    cp -a /config/miplib/lib/*.so /root/dao/prog/miplib/lib
  else
    bashio::log.info "Building new miplib-binaries"
    bash ./build_mip.sh
  fi
  export PMIP_CBC_LIBRARY="/root/dao/prog/miplib/lib/libCbc.so"
  export LD_LIBRARY_PATH="/root/dao/prog/miplib/lib"
  echo 'export PMIP_CBC_LIBRARY="/root/dao/prog/miplib/lib/libCbc.so"' >> ~/.bashrc
  echo 'export LD_LIBRARY_PATH="/root/dao/prog/miplib/lib/"' >> ~/.bashrc
fi

cd /root/dao/webserver/
gunicorn --config gunicorn_config.py app:app &

cd /root/dao/prog
bash ./watchdog.sh python3 da_scheduler.py








