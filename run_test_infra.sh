#!/usr/bin/env bash

docker run \
    -d \
    --rm \
    -e LOCALSTACK_HOSTNAME="localhost" \
    -e SERVICES="s3" \
    -p 8080:8080 \
    -p 443:443 \
    -p 4572:4572 \
    -p 4590-4593:4590-4593 \
    -v "/tmp/localstack:/tmp/localstack" \
    -v "/var/run/docker.sock:/var/run/docker.sock" \
    -e DOCKER_HOST="unix:///var/run/docker.sock" \
    -e HOST_TMP_FOLDER="/tmp/localstack" \
    "localstack/localstack:0.8.7"
