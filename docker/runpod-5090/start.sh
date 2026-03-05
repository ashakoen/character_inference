#!/bin/bash
# Startup script for FLUX.1-dev inference server
# Downloads model files on first boot, then starts the server
set -e

MODEL_DIR="/workspace/models"
FLOW_PATH="${MODEL_DIR}/flux1-dev.safetensors"
AE_PATH="${MODEL_DIR}/ae.safetensors"

mkdir -p "${MODEL_DIR}"

# Download models from HuggingFace if not already cached on the network volume
if [ ! -f "${FLOW_PATH}" ] || [ ! -f "${AE_PATH}" ]; then
    echo "First boot: downloading FLUX.1-dev model files to network volume..."
    echo "This will take 5-15 minutes depending on bandwidth (~24 GB total)."
    python -c "
from huggingface_hub import hf_hub_download
import os

repo = 'black-forest-labs/FLUX.1-dev'
dest = '${MODEL_DIR}'

if not os.path.exists('${FLOW_PATH}'):
    print('Downloading flux1-dev.safetensors (~24 GB)...')
    hf_hub_download(repo, 'flux1-dev.safetensors', local_dir=dest)
    print('Done.')

if not os.path.exists('${AE_PATH}'):
    print('Downloading ae.safetensors (~335 MB)...')
    hf_hub_download(repo, 'ae.safetensors', local_dir=dest)
    print('Done.')

print('All model files ready.')
"
    echo "Model download complete."
else
    echo "Model files found on network volume, skipping download."
fi

echo "Starting FLUX.1-dev inference server..."
cd /app/character_inference
exec python main.py --config-path /app/character_inference/config-dev-5090.json --port 8088 --host 0.0.0.0
