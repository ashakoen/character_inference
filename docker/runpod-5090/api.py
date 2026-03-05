import os
import uuid
import time
import asyncio
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


@app.post("/generate")
def generate(args: GenerateArgs, format: str = Query(default="json")):
    """
    Generates an image from the Flux flow transformer.

    When format=json (default), returns JSON with generation parameters and
    temporary image download URL(s). When format=stream, returns raw JPEG bytes
    for backward compatibility.
    """
    pipeline_args = args.model_dump(exclude={"num_images", "jpeg_quality"})

    if format == "stream":
        result = app.state.model.generate(**pipeline_args)
        return StreamingResponse(result, media_type="image/jpeg")

    request_id = str(uuid.uuid4())
    start_time = time.time()

    try:
        if args.num_images > 1:
            images_list, seed = app.state.model.generate(
                **pipeline_args,
                num_images=args.num_images,
                jpeg_quality=args.jpeg_quality,
                return_individual=True,
            )
            outputs = []
            for idx, img_bytes in enumerate(images_list):
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
            result, seed = app.state.model.generate(
                **pipeline_args,
                num_images=1,
                jpeg_quality=args.jpeg_quality,
                return_seed=True,
            )
            image_id = f"{request_id}_0"
            filepath = os.path.join(TEMP_IMAGE_DIR, f"{image_id}.jpg")
            with open(filepath, "wb") as f:
                f.write(result.getvalue())
            outputs = [{
                "url": f"/images/{image_id}.jpg",
                "width": args.width,
                "height": args.height,
            }]
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
