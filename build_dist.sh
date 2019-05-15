#!/usr/bin/env bash

set -ex

OS_NAME=$1

pip install -r requirements.txt
pyinstaller pyinstaller.py --name s3conf --onefile --hidden-import=configparser --additional-hooks-dir=hooks
rm -rf build s3conf.spec
cd dist
tar czf s3conf.$OS_NAME.tar.gz s3conf
cd ..
