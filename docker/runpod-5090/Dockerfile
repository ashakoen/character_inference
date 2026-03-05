FROM runpod/pytorch:1.0.3-cu1281-torch280-ubuntu2204

RUN apt-get update && apt-get install -y --no-install-recommends \
    tmux nvtop htop libturbojpeg0-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone inference repo
RUN git clone https://github.com/Otnielush/character_inference.git
WORKDIR /app/character_inference

# Install dependencies (add para-attn missing from requirements_docker.txt)
RUN pip install --no-cache-dir -r requirements_docker.txt && \
    pip install --no-cache-dir para-attn

# Config for RTX 5090 (32GB): FP8 everything, no offloading, no compilation
COPY config-dev-5090.json /app/character_inference/config-dev-5090.json

# Add bearer token auth middleware (patches api.py used by main.py)
COPY auth_middleware.py /app/character_inference/auth_middleware.py
RUN sed -i '/^app = FastAPIApp()/a\\nfrom auth_middleware import BearerAuthMiddleware\napp.add_middleware(BearerAuthMiddleware)' api.py

# Startup script: downloads models on first boot, then runs main.py
COPY start.sh /app/character_inference/start.sh
RUN chmod +x /app/character_inference/start.sh

# HF cache on network volume
ENV HF_HOME="/workspace/hf"
ENV HF_HUB_CACHE="/workspace/hf"

# Reduce CUDA memory fragmentation
ENV PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"

# LoRA storage
RUN mkdir -p /lora_styles

EXPOSE 8088

CMD ["/app/character_inference/start.sh"]
