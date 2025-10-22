#!/bin/bash
set -e

MARCH="-march=native"
EXTRAFLAGS="--with-gcc-arch=native"
if [ "$1" == "generic" ]; then
  MARCH=""
  EXTRAFLAGS=""
fi
[ ! -z $MARCH ] && echo "Compiling for native cpu!! This library will not be portable to other cpu's!!!" || true

CXXFLAGS="${MARCH} -O3"

if [ -d ~/build ]; then rm -rf ~/build; fi
mkdir -p ~/build
cd ~/build

wget -qnH https://raw.githubusercontent.com/coin-or/coinbrew/master/coinbrew
chmod +x coinbrew

./coinbrew build Cbc@master ADD_CXXFLAGS="${CXXFLAGS}" --no-prompt --prefix=prog/ --tests=none --enable-cbc-parallel --enable-relocatable --no-third-party ${EXTRAFLAGS=}

echo
echo "Compilation finished! Moving lib into place."

if [ -d /root/dao/prog/miplib/lib ]; then rm -rf /root/dao/prog/miplib/lib; fi
mkdir -p /root/dao/prog/miplib/lib
cp -a ~/build/prog/lib/*.so* /root/dao/prog/miplib/lib

if [ -d /config/miplib/lib ]; then
  echo "Backing up the previously compiled libraries."
  rm -rf /config/miplib/lib.bck;
  mv /config/miplib/lib /config/miplib/lib.bck;
fi
mkdir -p /config/miplib/lib
cp -a ~/build/prog/lib/*.so* /config/miplib/lib

echo
echo "All done. Hit any key to exit... (15 minutes timeout)"
read -s -n 1 -t 900 || true && echo All done, exiting

