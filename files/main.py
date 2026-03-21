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

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from contextlib import asynccontextmanager
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
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Routes ─────────────────────────────────────────────────────────────────

@app.get("/api/status")
def status():
    return {
        "source": data.source,
        "total" : data.count(),
    }


@app.get("/api/pairs")
def list_pairs(
    page : int = Query(1,  ge=1),
    limit: int = Query(20, ge=1, le=100),
    q    : str = Query("", description="Filter by defect name or fiche number"),
):
    """
    Paginated list of pairs — lightweight, no image data.
    """
    skip   = (page - 1) * limit
    pairs, total = data.list_pairs(skip=skip, limit=limit, query=q)
    return {
        "total" : total,
        "page"  : page,
        "limit" : limit,
        "pages" : (total + limit - 1) // limit,
        "items" : pairs,
    }


@app.get("/api/pairs/{pair_id}")
def get_pair(pair_id: str):
    """Full pair detail — commentary sections, metadata. No image."""
    pair = data.get_pair(pair_id)
    if not pair:
        raise HTTPException(status_code=404, detail="Pair not found")
    return pair


@app.get("/api/pairs/{pair_id}/image")
def get_image(pair_id: str):
    """Returns the raw image bytes — Angular uses this as <img [src]>."""
    pair = data.get_pair(pair_id)
    if not pair:
        raise HTTPException(status_code=404, detail="Pair not found")
    if not pair.get("image_b64"):
        raise HTTPException(status_code=404, detail="No image for this pair")

    img_bytes = base64.b64decode(pair["image_b64"])
    ext       = pair.get("image_ext", "jpeg").lower()
    media     = "image/png" if ext == "png" else "image/jpeg"
    return Response(content=img_bytes, media_type=media)
