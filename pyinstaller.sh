#!/usr/bin/env bash

rm -rf dist build s3conf.spec
pyinstaller pyinstaller.py --name s3conf --onefile --hidden-import=configparser --additional-hooks-dir=hooks
rm -rf build s3conf.spec
