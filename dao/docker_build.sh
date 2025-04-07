docker buildx build \
   --build-arg BUILD_ARCH=amd64 \
   --build-arg BUILD_FROM=ghcr.io/hassio-addons/debian-base/amd64:stable \
   --build-arg BUILD_VERSION=2025.3.1 \
   -t dao:latest \
   https://github.com/corneel27/day-ahead.git#main:dao
