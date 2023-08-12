#!/bin/bash
wget https://dl.min.io/server/minio/release/linux-arm64/minio https://dl.min.io/server/mc/release/linux-arm64/mc || exit 1
chmod a+x minio mc || exit 1
