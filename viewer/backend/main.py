"""
Dataset Viewer — FastAPI Backend
=================================
Serves extracted ITSEOA training pairs to the Angular frontend.

Data source priority:
  1. MongoDB (if reachable)
  2. Local finetuning_dataset.json (fallback)

Run:
    uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from contextlib import asynccontextmanager
from typing import Optional
import base64

from data import DataLayer

data = DataLayer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    data.connect()
    print(f"Data source: {data.source}")
    print(f"Total pairs : {data.count()}")
    yield


app = FastAPI(title="ITSEOA Dataset Viewer", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Routes ─────────────────────────────────────────────────────────────────


@app.get("/api/status")
def status():
    return {
        "source": data.source,
        "total": data.count(),
    }


@app.get("/api/pairs")
def list_pairs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    q: str = Query("", description="Filter by defect name or fiche number"),
):
    skip = (page - 1) * limit
    pairs, total = data.list_pairs(skip=skip, limit=limit, query=q)
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
        "items": pairs,
    }


@app.get("/api/pairs/{pair_id}")
def get_pair(pair_id: str):
    pair = data.get_pair(pair_id)
    if not pair:
        raise HTTPException(status_code=404, detail="Pair not found")
    return pair


@app.get("/api/pairs/{pair_id}/image")
def get_image(pair_id: str):
    pair = data.get_pair(pair_id)
    if not pair:
        raise HTTPException(status_code=404, detail="Pair not found")
    if not pair.get("image_b64"):
        raise HTTPException(status_code=404, detail="No image for this pair")

    img_bytes = base64.b64decode(pair["image_b64"])
    ext = pair.get("image_ext", "jpeg").lower()
    media = "image/png" if ext == "png" else "image/jpeg"
    return Response(content=img_bytes, media_type=media)


@app.post("/api/pairs", status_code=201)
async def create_pair(
    image: UploadFile = File(...),
    defect: str = Form(...),
    fiche: str = Form(""),
    commentary: str = Form(""),
    severity: str = Form(""),
    source_pdf: str = Form(""),
):
    """
    Upload a new image + commentary pair.
    Only image and defect name are required.
    """
    # Validate image type
    allowed = {"image/jpeg", "image/png", "image/jpg"}
    if image.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Image must be JPEG or PNG")

    # Read and encode image
    img_bytes = await image.read()
    if len(img_bytes) > 20 * 1024 * 1024:  # 20 MB limit
        raise HTTPException(status_code=400, detail="Image too large (max 20 MB)")

    img_b64 = base64.b64encode(img_bytes).decode("utf-8")
    ext = image.content_type.split("/")[-1].replace("jpg", "jpeg")

    record = {
        "fiche": fiche.strip(),
        "defect": defect.strip(),
        "page": 0,
        "layout": "manual",
        "source_pdf": source_pdf.strip() or "manual_upload",
        "commentary": {
            "full": commentary.strip(),
            "intro": "",
            "causes": "",
            "gravite": severity.strip(),
            "suites": "",
        },
        "image_b64": img_b64,
        "image_ext": ext,
        "source_type": "manual_upload",
        "validated": False,
    }

    created = data.create_pair(record)
    return created
