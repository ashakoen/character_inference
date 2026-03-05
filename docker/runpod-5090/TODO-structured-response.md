# Task: Structured JSON Response with Temp Image URL

**Status:** Planned
**Priority:** Next

## Goal
Transform `POST /generate` from streaming raw JPEG bytes to returning a JSON response with generation parameters and a temporary download URL, matching the pattern used by Replicate and Fal.ai.

## Current Behavior
`POST /generate` → streams raw JPEG bytes (`image/jpeg`)

## Target Behavior
`POST /generate` → returns JSON (`application/json`):
```json
{
  "id": "a1b2c3d4-5678-...",
  "status": "success",
  "input": {
    "prompt": "A fluffy orange cat...",
    "width": 1024,
    "height": 1024,
    "num_steps": 28,
    "guidance": 3.5,
    "seed": 12345,
    "strength": 1.0
  },
  "output": {
    "url": "https://<pod>:8088/images/a1b2c3d4-5678-...jpg",
    "width": 1024,
    "height": 1024,
    "seed": 12345
  },
  "metrics": {
    "generation_time_seconds": 4.2
  }
}
```

## Implementation Steps

### 1. Add image storage + serving
- Create `/tmp/generated_images/` as temp image dir (ephemeral, not network volume)
- Add `GET /images/{image_id}.jpg` static file route to serve generated images
- Generate UUID for each image filename

### 2. Add cleanup task
- Background task that deletes images older than 30 minutes
- Use FastAPI `BackgroundTasks` or periodic cleanup on each request

### 3. Modify `/generate` response
- Save JPEG to temp dir instead of streaming
- Time the generation (`time.time()` around the pipeline call)
- Extract actual seed used (pass `return_seed=True` to pipeline)
- Return JSON with all input params, output URL, seed, and timing

### 4. Add new API params to GenerateArgs
- `num_images` (int, default 1) — return array of output URLs
- `jpeg_quality` (int, default 99) — control JPEG compression

### 5. Update OpenAPI spec
- New response schema with input/output/metrics
- New `GET /images/{id}` endpoint doc
- Updated examples

## Files to Modify/Create
- `api.py` — new response format, static file route, cleanup logic
- `openapi.yaml` — updated spec
- `Dockerfile` — `mkdir -p /tmp/generated_images` (minor)

## Design Considerations
- Auth middleware must protect `/images/` route too (already covered by ASGI middleware on all HTTP)
- Temp images on pod local storage, not network volume — ephemeral is correct
- Consider `?format=stream` query param to preserve raw JPEG streaming for backward compat
- For `num_images > 1`, return `output` as array of objects
- Seed in response is important — lets users reproduce exact results
