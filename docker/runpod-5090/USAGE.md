# FLUX.1-dev RunPod API Usage Guide

## Authentication

All requests require a Bearer token set via the `AUTH_TOKEN` environment variable on the pod.

```
Authorization: Bearer <your-token>
```

## Generate an Image

```bash
curl -X POST "https://<pod-id>-8088.proxy.runpod.net/generate" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer <your-token>" \
    -d '{
        "prompt": "A fluffy orange cat sitting on a windowsill at sunset",
        "width": 1024,
        "height": 1024,
        "num_steps": 28,
        "guidance": 3.5,
        "seed": 42
    }' \
    --output image.jpg
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | string | required | Text prompt. Supports weighting: `(word:1.5)` increases, `[word]` decreases attention |
| `width` | int | 720 | Image width in pixels |
| `height` | int | 1024 | Image height in pixels |
| `num_steps` | int | 24 | Diffusion steps. More = better quality, slower. 20-30 typical |
| `guidance` | float | 3.5 | Prompt adherence. Higher = follows prompt more closely. 1.0-10.0 typical |
| `seed` | int | random | Random seed for reproducible results |
| `strength` | float | 1.0 | img2img strength. 1.0 = full generation, lower preserves init image |
| `init_image` | string | null | Base64-encoded image for img2img generation |

### Recommended Resolutions

| Aspect Ratio | Resolution | Notes |
|-------------|------------|-------|
| 1:1 Square | 1024x1024 | Default quality target |
| 16:9 Landscape | 1280x720 | Cinematic wide |
| 9:16 Portrait | 720x1280 | Mobile/vertical |
| 4:3 Landscape | 1024x768 | Standard landscape |
| 3:4 Portrait | 768x1024 | Standard portrait |

Resolutions above ~1M total pixels (e.g. 1536x1536) may cause OOM errors on RTX 5090 with current config.

### Prompt Weighting

The prompt supports attention weighting syntax:
- `(important word)` — increases weight by 1.1x
- `(important word:1.5)` — increases weight by 1.5x
- `[less important]` — decreases weight by 1.1x
- `((very important))` — nesting stacks: 1.1 x 1.1 = 1.21x

Example:
```bash
curl -X POST "https://<pod-id>-8088.proxy.runpod.net/generate" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer <your-token>" \
    -d '{
        "prompt": "A (beautiful:1.3) sunset over mountains with ((dramatic lighting)) and [minimal clouds]",
        "width": 1280,
        "height": 720,
        "num_steps": 28
    }' \
    --output landscape.jpg
```

## Load a LoRA

LoRA files must already exist on the pod filesystem (e.g. `/workspace/loras/`). LoRAs are fused directly into model weights — they add zero persistent VRAM.

```bash
curl -X POST "https://<pod-id>-8088.proxy.runpod.net/lora" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer <your-token>" \
    -d '{
        "path": "/workspace/loras/my-style-lora.safetensors",
        "scale": 0.8,
        "name": "my-style",
        "action": "load"
    }'
```

### Response
```json
{"status": "success"}
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | null | Absolute path to .safetensors file on the pod |
| `scale` | float | 1.0 | LoRA weight strength. 0.5-1.0 typical for styles |
| `name` | string | derived from filename | Identifier used for unloading |
| `action` | string | "load" | Either "load" or "unload" |

## Unload a LoRA

```bash
curl -X POST "https://<pod-id>-8088.proxy.runpod.net/lora" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer <your-token>" \
    -d '{
        "name": "my-style",
        "action": "unload"
    }'
```

## Image-to-Image Generation

Pass a base64-encoded image as `init_image` with a `strength` value:

```bash
# Encode an image to base64
BASE64_IMG=$(base64 -i input.jpg)

curl -X POST "https://<pod-id>-8088.proxy.runpod.net/generate" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer <your-token>" \
    -d "{
        \"prompt\": \"Same scene but in watercolor painting style\",
        \"width\": 1024,
        \"height\": 1024,
        \"num_steps\": 28,
        \"strength\": 0.7,
        \"init_image\": \"${BASE64_IMG}\"
    }" \
    --output watercolor.jpg
```

`strength` controls how much of the original image to preserve:
- `1.0` = ignore init image entirely (full text-to-image)
- `0.7` = moderate transformation
- `0.3` = subtle changes, preserves most of original
