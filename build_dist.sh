#!/usr/bin/env bash

pip install -r requirements.txt
pyinstaller pyinstaller.py --name s3conf --onefile --hidden-import=configparser --additional-hooks-dir=hooks
rm -rf build s3conf.spec