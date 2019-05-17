#!/usr/bin/env sh

set -ex

#apt-get install -y gcc make g++ build-essential binutils
apk add make g++
#wget http://www.musl-libc.org/releases/musl-1.1.22.tar.gz
#tar xzf musl-1.1.22.tar.gz
#cd musl-1.1.22
#./configure
#make
#make install
#cd ..

pip install patchelf-wrapper scons
#pip install https://github.com/JonathonReinhart/staticx/archive/master.zip
pip uninstall staticx
CC=/usr/bin/x86_64-alpine-linux-musl-gcc pip install https://github.com/sbneto/staticx/archive/exiting-archive.zip

pip install -r requirements.txt
pyinstaller --debug bootloader pyinstaller.py --name s3conf-$(uname -s)-$(uname -m) --onefile --hidden-import=configparser --additional-hooks-dir=hooks
rm -rf build s3conf-$(uname -s)-$(uname -m).spec
export S3CONF_CLIENT=s3conf-$(uname -s)-$(uname -m)
