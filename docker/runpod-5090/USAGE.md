# FLUX.1-dev RunPod API Usage Guide

## Authentication

All requests require a Bearer token set via the `AUTH_TOKEN` environment variable on the pod.

```
Authorization: Bearer <your-token>
```

## Response Formats

The `POST /generate` endpoint supports three response formats via the `?format=` query parameter:

| Format | Description |
|--------|-------------|
| `json` (default) | Blocks until done, returns JSON with image URL(s), seed, and timing |
| `sse` | Streams Server-Sent Events with per-step progress, then final result |
| `stream` | Returns raw JPEG bytes (legacy) |

---

## Generate an Image (JSON format)

```bash
curl -X POST "https://<pod-id>-8088.proxy.runpod.net/generate" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer <your-token>" \
    -d '{
        "prompt": "A fluffy orange cat sitting on a windowsill at sunset",
        "width": 1024,
        "height": 1024,
        "num_steps": 28
    }'
```

### Response
```json
{
  "id": "62e38e10-3893-497f-b58b-46fa3c7dc7eb",
  "status": "success",
  "input": {
    "prompt": "A fluffy orange cat sitting on a windowsill at sunset",
    "width": 1024,
    "height": 1024,
    "num_steps": 28,
    "guidance": 3.5,
    "seed": 1244825697,
    "strength": 1.0,
    "num_images": 1,
    "jpeg_quality": 99
  },
  "output": [
    {
      "url": "/images/62e38e10-3893-497f-b58b-46fa3c7dc7eb_0.jpg",
      "width": 1024,
      "height": 1024
    }
  ],
  "seed": 1244825697,
  "metrics": {
    "generation_time_seconds": 6.669
  }
}
```

### Download the Image
The `output[].url` is relative. Prepend the pod base URL:

```bash
curl "https://<pod-id>-8088.proxy.runpod.net/images/62e38e10-3893-497f-b58b-46fa3c7dc7eb_0.jpg" \
    -H "Authorization: Bearer <your-token>" \
    --output image.jpg
```

Images are stored temporarily and auto-deleted after 30 minutes.

---

## Generate with Progress (SSE format)

Use `?format=sse` to receive Server-Sent Events with real-time progress updates during generation.

### curl Example
```bash
curl -N -X POST "https://<pod-id>-8088.proxy.runpod.net/generate?format=sse" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer <your-token>" \
    -d '{"prompt": "A fluffy orange cat", "width": 1024, "height": 1024, "num_steps": 28}'
```

### SSE Event Sequence

**1. Starting event** (sent immediately):
```
data: {"id":"62e38e10-...","status":"starting"}
```

**2. Progress events** (one per diffusion step):
```
data: {"id":"62e38e10-...","status":"generating","step":1,"total_steps":28}
data: {"id":"62e38e10-...","status":"generating","step":2,"total_steps":28}
...
data: {"id":"62e38e10-...","status":"generating","step":28,"total_steps":28}
```

**3. Complete event** (with full result):
```
data: {"id":"62e38e10-...","status":"complete","input":{...},"output":[{"url":"/images/...","width":1024,"height":1024}],"seed":1244825697,"metrics":{"generation_time_seconds":6.669}}
```

**On error:**
```
data: {"id":"62e38e10-...","status":"error","message":"CUDA out of memory..."}
```

### JavaScript Client Example (fetch + ReadableStream)

```javascript
async function generateWithProgress(baseUrl, token, params, onProgress, onComplete, onError) {
  const response = await fetch(`${baseUrl}/generate?format=sse`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(params),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop(); // keep incomplete line in buffer

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const data = JSON.parse(line.slice(6));

      switch (data.status) {
        case 'starting':
          // Generation started
          break;
        case 'generating':
          onProgress({
            step: data.step,
            totalSteps: data.total_steps,
            percent: Math.round((data.step / data.total_steps) * 100),
          });
          break;
        case 'complete':
          onComplete({
            id: data.id,
            imageUrl: `${baseUrl}${data.output[0].url}`,
            seed: data.seed,
            generationTime: data.metrics.generation_time_seconds,
          });
          break;
        case 'error':
          onError(data.message);
          break;
      }
    }
  }
}

// Usage
generateWithProgress(
  'https://pod-id-8088.proxy.runpod.net',
  'your-token',
  { prompt: 'A fluffy orange cat', width: 1024, height: 1024, num_steps: 28 },
  (progress) => console.log(`Step ${progress.step}/${progress.totalSteps} (${progress.percent}%)`),
  (result) => console.log('Done!', result.imageUrl),
  (error) => console.error('Error:', error),
);
```

### React Hook Example

```javascript
function useImageGeneration(baseUrl, token) {
  const [status, setStatus] = useState('idle'); // idle | generating | complete | error
  const [progress, setProgress] = useState({ step: 0, totalSteps: 0, percent: 0 });
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const generate = useCallback(async (params) => {
    setStatus('generating');
    setProgress({ step: 0, totalSteps: params.num_steps || 24, percent: 0 });
    setResult(null);
    setError(null);

    try {
      const response = await fetch(`${baseUrl}/generate?format=sse`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(params),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = JSON.parse(line.slice(6));

          if (data.status === 'generating') {
            setProgress({
              step: data.step,
              totalSteps: data.total_steps,
              percent: Math.round((data.step / data.total_steps) * 100),
            });
          } else if (data.status === 'complete') {
            setStatus('complete');
            setResult({
              id: data.id,
              imageUrl: `${baseUrl}${data.output[0].url}`,
              seed: data.seed,
              input: data.input,
              generationTime: data.metrics.generation_time_seconds,
            });
          } else if (data.status === 'error') {
            setStatus('error');
            setError(data.message);
          }
        }
      }
    } catch (err) {
      setStatus('error');
      setError(err.message);
    }
  }, [baseUrl, token]);

  return { generate, status, progress, result, error };
}
```

---

## Parameters

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
| `num_images` | int | 1 | Number of images to generate (1-4) |
| `jpeg_quality` | int | 99 | JPEG compression quality (1-100) |

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

---

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
    }"
```

`strength` controls how much of the original image to preserve:
- `1.0` = ignore init image entirely (full text-to-image)
- `0.7` = moderate transformation
- `0.3` = subtle changes, preserves most of original
