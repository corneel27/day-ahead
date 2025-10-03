if [ -d ""~/build"" ]; then rm -rf ~/build; fi
mkdir -p ~/build
cd ~/build

wget -nH https://raw.githubusercontent.com/coin-or/coinbrew/master/coinbrew
chmod +x coinbrew

./coinbrew build Cbc@master ADD_CXXFLAGS="-march=native -O3" --no-prompt --prefix=prog/ --tests=none --enable-cbc-parallel --enable-relocatable --no-third-party --with-gcc-arch=native

if [ -d "/root/dao/prog/miplib/lib" ]; then rm -rf /root/dao/prog/miplib/lib; fi
mkdir -p /root/dao/prog/miplib/lib
cp -a ~/build/prog/lib/*.so* /root/dao/prog/miplib/lib
mkdir -p /config/miplib/lib
cp -a ~/build/prog/lib/*.so* /config/miplib/lib