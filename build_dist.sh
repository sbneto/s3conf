#!/usr/bin/env bash

pyinstaller pyinstaller.py --name s3conf --onefile --hidden-import=configparser --additional-hooks-dir=hooks
