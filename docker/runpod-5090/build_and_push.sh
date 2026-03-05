#!/bin/bash
# Build and push the FLUX inference Docker image to GHCR
# Usage: GHCR_TOKEN=xxx ./build_and_push.sh
#
# Prerequisites:
#   - Docker with buildx
#   - GHCR personal access token with write:packages scope

set -euo pipefail

REGISTRY="ghcr.io"
OWNER="ashakoen"
IMAGE_NAME="flux-inference"
TAG="${1:-latest}"
FULL_IMAGE="${REGISTRY}/${OWNER}/${IMAGE_NAME}:${TAG}"

if [ -z "${GHCR_TOKEN:-}" ]; then
    echo "ERROR: Set GHCR_TOKEN environment variable"
    echo "  Create a token at https://github.com/settings/tokens with write:packages scope"
    exit 1
fi

echo "Building ${FULL_IMAGE}..."

echo "${GHCR_TOKEN}" | docker login ${REGISTRY} -u ${OWNER} --password-stdin

docker build -t "${FULL_IMAGE}" -f Dockerfile .

echo "Pushing ${FULL_IMAGE}..."
docker push "${FULL_IMAGE}"

echo "Done: ${FULL_IMAGE}"
