#!/bin/bash
# Deploy FLUX.1-dev image generation server on RunPod
# Usage: RUNPOD_API_KEY=xxx HF_TOKEN=hf_xxx AUTH_TOKEN=xxx ./deploy_flux.sh
#
# Prerequisites:
#   - Network volume 1687hufr6p in EUR-NO-1
#   - HuggingFace token with access to black-forest-labs/FLUX.1-dev
#   - Docker image pushed to GHCR (built via docker/flux/build_and_push.sh)
#   - GHCR registry auth saved in RunPod (id: cmmdvp3zq008jl407tuvt2w8g)
#
# First boot downloads ~34 GB of model files to the network volume.
# Subsequent boots use the cached models and start much faster.

set -euo pipefail

# --- Configuration ---
POD_NAME="${POD_NAME:-flux-dev-inference}"
GPU_TYPE="NVIDIA GeForce RTX 5090"
GPU_COUNT=1
IMAGE="${FLUX_IMAGE:-ghcr.io/ashakoen/flux-inference:latest}"
VOLUME_ID="1687hufr6p"
CONTAINER_DISK_GB=30
VOLUME_MOUNT="/workspace"
DATA_CENTER="EUR-NO-1"
REGISTRY_AUTH_ID="cmmdvp3zq008jl407tuvt2w8g"

# --- Validation ---
if [ -z "${RUNPOD_API_KEY:-}" ]; then
    echo "ERROR: Set RUNPOD_API_KEY environment variable"
    exit 1
fi

if [ -z "${HF_TOKEN:-}" ]; then
    echo "ERROR: Set HF_TOKEN environment variable (needs access to black-forest-labs/FLUX.1-dev)"
    exit 1
fi

if [ -z "${AUTH_TOKEN:-}" ]; then
    echo "ERROR: Set AUTH_TOKEN environment variable (bearer token for API access)"
    exit 1
fi

echo "Deploying ${POD_NAME}..."
echo "  GPU: ${GPU_TYPE}"
echo "  Image: ${IMAGE}"
echo "  Volume: ${VOLUME_ID} (${DATA_CENTER})"
echo ""

# --- Create Pod via GraphQL API (supports containerRegistryAuthId) ---
GQL_QUERY='mutation {
  podFindAndDeployOnDemand(input: {
    name: "'"${POD_NAME}"'"
    imageName: "'"${IMAGE}"'"
    gpuTypeId: "'"${GPU_TYPE}"'"
    gpuCount: '"${GPU_COUNT}"'
    containerDiskInGb: '"${CONTAINER_DISK_GB}"'
    networkVolumeId: "'"${VOLUME_ID}"'"
    volumeMountPath: "'"${VOLUME_MOUNT}"'"
    ports: "8088/http,22/tcp"
    dataCenterId: "'"${DATA_CENTER}"'"
    containerRegistryAuthId: "'"${REGISTRY_AUTH_ID}"'"
    env: [
      { key: "HF_TOKEN", value: "'"${HF_TOKEN}"'" }
      { key: "HF_HOME", value: "/workspace/hf" }
      { key: "HF_HUB_CACHE", value: "/workspace/hf" }
      { key: "AUTH_TOKEN", value: "'"${AUTH_TOKEN}"'" }
    ]
  }) {
    id
    name
    desiredStatus
    imageName
    machineId
  }
}'

RESPONSE=$(curl -s --max-time 30 -X POST "https://api.runpod.io/graphql?api_key=${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "import json; print(json.dumps({'query': '''${GQL_QUERY}'''}))")")

# --- Parse Response ---
POD_ID=$(echo "$RESPONSE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'errors' in d:
    print('', end='')
else:
    print(d.get('data',{}).get('podFindAndDeployOnDemand',{}).get('id',''))
" 2>/dev/null || true)

if [ -z "$POD_ID" ]; then
    echo "ERROR: Failed to create pod. Raw API response:"
    echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
    exit 1
fi

echo "Pod created: ${POD_ID}"
echo ""
echo "Inference endpoint (once ready):"
echo "  https://${POD_ID}-8088.proxy.runpod.net/generate"
echo ""
echo "SSH (check RunPod dashboard for port):"
echo "  ssh root@<ip> -p <port> -i ~/.ssh/id_ed25519"
echo ""
echo "NOTE: First boot downloads ~34 GB of models. This takes 5-15 min depending on bandwidth."
echo "      Check logs in RunPod dashboard to monitor progress."
echo ""
echo "Test (after models are loaded):"
echo "  curl -s https://${POD_ID}-8088.proxy.runpod.net/generate \\"
echo "    -H 'Authorization: Bearer ${AUTH_TOKEN}' \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"prompt\":\"a photo of a cat astronaut floating in space\",\"width\":1024,\"height\":1024,\"num_steps\":28}' \\"
echo "    --output test.jpg"
