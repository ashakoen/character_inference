import os
import json
import uuid
import time
import asyncio
import threading
import queue
from typing import Literal, Optional, TYPE_CHECKING

import numpy as np
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from pydantic import BaseModel, Field
from platform import system

if TYPE_CHECKING:
    from flux_pipeline import FluxPipeline

if system() == "Windows":
    MAX_RAND = 2**16 - 1
else:
    MAX_RAND = 2**32 - 1

TEMP_IMAGE_DIR = "/tmp/generated_images"
IMAGE_TTL_SECONDS = 1800
CLEANUP_INTERVAL_SECONDS = 300
os.makedirs(TEMP_IMAGE_DIR, exist_ok=True)


class AppState:
    model: "FluxPipeline"


class FastAPIApp(FastAPI):
    state: AppState


class LoraArgs(BaseModel):
    scale: Optional[float] = 1.0
    path: Optional[str] = None
    name: Optional[str] = None
    action: Optional[Literal["load", "unload"]] = "load"


class LoraLoadResponse(BaseModel):
    status: Literal["success", "error"]
    message: Optional[str] = None


class GenerateArgs(BaseModel):
    prompt: str
    width: Optional[int] = Field(default=720)
    height: Optional[int] = Field(default=1024)
    num_steps: Optional[int] = Field(default=24)
    guidance: Optional[float] = Field(default=3.5)
    seed: Optional[int] = Field(
        default_factory=lambda: np.random.randint(0, MAX_RAND), gt=0, lt=MAX_RAND
    )
    strength: Optional[float] = 1.0
    init_image: Optional[str] = None
    num_images: Optional[int] = Field(default=1, ge=1, le=4)
    jpeg_quality: Optional[int] = Field(default=99, ge=1, le=100)


app = FastAPIApp()


async def _periodic_cleanup():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        now = time.time()
        try:
            for fname in os.listdir(TEMP_IMAGE_DIR):
                fpath = os.path.join(TEMP_IMAGE_DIR, fname)
                if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > IMAGE_TTL_SECONDS:
                    os.unlink(fpath)
        except Exception:
            pass


@app.on_event("startup")
async def start_cleanup_task():
    asyncio.create_task(_periodic_cleanup())


def _save_images(request_id, args, result, seed, is_multi):
    """Save generated image(s) to temp dir and return output list."""
    outputs = []
    if is_multi:
        for idx, img_bytes in enumerate(result):
            image_id = f"{request_id}_{idx}"
            filepath = os.path.join(TEMP_IMAGE_DIR, f"{image_id}.jpg")
            with open(filepath, "wb") as f:
                f.write(img_bytes.getvalue())
            outputs.append({
                "url": f"/images/{image_id}.jpg",
                "width": args.width,
                "height": args.height,
            })
    else:
        image_id = f"{request_id}_0"
        filepath = os.path.join(TEMP_IMAGE_DIR, f"{image_id}.jpg")
        with open(filepath, "wb") as f:
            f.write(result.getvalue())
        outputs.append({
            "url": f"/images/{image_id}.jpg",
            "width": args.width,
            "height": args.height,
        })
    return outputs


@app.post("/generate")
def generate(args: GenerateArgs, format: str = Query(default="json")):
    """
    Generates an image from the Flux flow transformer.

    Formats:
    - json (default): Returns JSON with generation params and temp image URL(s)
    - stream: Returns raw JPEG bytes (legacy)
    - sse: Streams Server-Sent Events with per-step progress, then final JSON result
    """
    pipeline_args = args.model_dump(exclude={"num_images", "jpeg_quality"})

    # Legacy: raw JPEG stream
    if format == "stream":
        result = app.state.model.generate(**pipeline_args)
        return StreamingResponse(result, media_type="image/jpeg")

    # SSE: stream progress events then final result
    if format == "sse":
        return StreamingResponse(
            _sse_generate(args, pipeline_args),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # Default: blocking JSON response
    request_id = str(uuid.uuid4())
    start_time = time.time()

    try:
        is_multi = args.num_images > 1
        if is_multi:
            result, seed = app.state.model.generate(
                **pipeline_args,
                num_images=args.num_images,
                jpeg_quality=args.jpeg_quality,
                return_individual=True,
            )
        else:
            result, seed = app.state.model.generate(
                **pipeline_args,
                num_images=1,
                jpeg_quality=args.jpeg_quality,
                return_seed=True,
            )
        outputs = _save_images(request_id, args, result, seed, is_multi)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"id": request_id, "status": "error", "message": str(e)},
        )

    generation_time = time.time() - start_time

    return JSONResponse(content={
        "id": request_id,
        "status": "success",
        "input": args.model_dump(exclude={"init_image"}),
        "output": outputs,
        "seed": seed,
        "metrics": {"generation_time_seconds": round(generation_time, 3)},
    })


def _sse_generate(args, pipeline_args):
    """Generator that yields SSE events with progress and final result."""
    request_id = str(uuid.uuid4())
    progress_queue = queue.Queue()
    result_holder = {}

    def progress_callback(step, total):
        progress_queue.put({"step": step, "total": total})

    def run_generation():
        try:
            is_multi = args.num_images > 1
            if is_multi:
                result, seed = app.state.model.generate(
                    **pipeline_args,
                    num_images=args.num_images,
                    jpeg_quality=args.jpeg_quality,
                    return_individual=True,
                    progress_callback=progress_callback,
                )
            else:
                result, seed = app.state.model.generate(
                    **pipeline_args,
                    num_images=1,
                    jpeg_quality=args.jpeg_quality,
                    return_seed=True,
                    progress_callback=progress_callback,
                )
            result_holder["result"] = result
            result_holder["seed"] = seed
            result_holder["is_multi"] = is_multi
        except Exception as e:
            result_holder["error"] = str(e)
        finally:
            progress_queue.put(None)  # signal done

    start_time = time.time()

    # Yield initial event
    yield f"data: {json.dumps({'id': request_id, 'status': 'starting'})}\n\n"

    # Start generation in background thread
    thread = threading.Thread(target=run_generation)
    thread.start()

    # Stream progress events
    while True:
        try:
            event = progress_queue.get(timeout=30)
        except queue.Empty:
            # Send keepalive
            yield ": keepalive\n\n"
            continue

        if event is None:
            break

        yield f"data: {json.dumps({'id': request_id, 'status': 'generating', 'step': event['step'], 'total_steps': event['total']})}\n\n"

    thread.join()

    generation_time = time.time() - start_time

    # Final event
    if "error" in result_holder:
        yield f"data: {json.dumps({'id': request_id, 'status': 'error', 'message': result_holder['error']})}\n\n"
    else:
        outputs = _save_images(
            request_id, args,
            result_holder["result"],
            result_holder["seed"],
            result_holder["is_multi"],
        )
        yield f"data: {json.dumps({'id': request_id, 'status': 'complete', 'input': args.model_dump(exclude={'init_image'}), 'output': outputs, 'seed': result_holder['seed'], 'metrics': {'generation_time_seconds': round(generation_time, 3)}})}\n\n"


@app.get("/images/{image_id}")
def get_image(image_id: str):
    """Serves a temporarily stored generated image."""
    basename = os.path.basename(image_id)
    if not basename.endswith(".jpg"):
        return JSONResponse(status_code=400, content={"error": "Invalid image ID"})
    filepath = os.path.join(TEMP_IMAGE_DIR, basename)
    if not os.path.isfile(filepath):
        return JSONResponse(status_code=404, content={"error": "Image not found or expired"})
    return FileResponse(filepath, media_type="image/jpeg")


@app.post("/lora", response_model=LoraLoadResponse)
def lora_action(args: LoraArgs):
    """
    Loads or unloads a LoRA checkpoint into / from the Flux flow transformer.

    Args:
        args (LoraArgs): Arguments for the LoRA action:

            - `scale`: The scaling factor for the LoRA weights.
            - `path`: The path to the LoRA checkpoint.
            - `name`: The name of the LoRA checkpoint.
            - `action`: The action to perform, either "load" or "unload".

    Returns:
        LoraLoadResponse: The status of the LoRA action.
    """
    try:
        if args.action == "load":
            app.state.model.load_lora(args.path, args.scale, args.name)
        elif args.action == "unload":
            app.state.model.unload_lora(args.name if args.name else args.path)
        else:
            return JSONResponse(
                content={
                    "status": "error",
                    "message": f"Invalid action, expected 'load' or 'unload', got {args.action}",
                },
                status_code=400,
            )
    except Exception as e:
        return JSONResponse(
            status_code=500, content={"status": "error", "message": str(e)}
        )
    return JSONResponse(status_code=200, content={"status": "success"})
