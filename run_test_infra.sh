#!/usr/bin/env bash

docker run \
    -d \
    --rm \
    -e MINIO_ACCESS_KEY=testtest \
    -e MINIO_SECRET_KEY=testtest \
    -p 9000:9000 \
    "minio/minio" \
    server /data
