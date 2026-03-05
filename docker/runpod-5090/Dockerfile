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

# Config for RTX 5090 (32GB): FP8 flow, bf16 T5/VAE, no offloading
COPY config-dev-5090.json /app/character_inference/config-dev-5090.json

# Patched api.py with structured JSON response + temp image URLs
COPY api.py /app/character_inference/api.py

# Patched flux_pipeline.py with into_individual_bytes() support
COPY flux_pipeline.py /app/character_inference/flux_pipeline.py

# Add bearer token auth middleware (patches api.py)
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

# LoRA storage + temp image storage
RUN mkdir -p /lora_styles /tmp/generated_images

EXPOSE 8088

CMD ["/app/character_inference/start.sh"]
