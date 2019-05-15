#!/usr/bin/env bash

set -ex

pip install -r requirements.txt
pyinstaller pyinstaller.py --name s3conf-$(uname -s)-$(uname -m) --onefile --hidden-import=configparser --additional-hooks-dir=hooks
rm -rf build s3conf-$(uname -s)-$(uname -m).spec
