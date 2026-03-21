"""
DataLayer
=========
Abstracts the data source behind a single interface.
Tries MongoDB first; falls back to the local JSON file if unavailable.

Configure via environment variables (or edit defaults here):
    MONGO_URI   — MongoDB connection string (default: mongodb://localhost:27017)
    MONGO_DB    — Database name            (default: inspection_db)
    MONGO_COLL  — Collection name          (default: itseoa_pairs)
    JSON_PATH   — Path to finetuning_dataset.json fallback
"""

import os
from datetime import datetime
import json
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "inspection_db")
MONGO_COLL = os.getenv("MONGO_COLL", "itseoa_pairs")

# Fallback: path to a finetuning_dataset.json produced by itseoa_extractor.py
# Adjust this to your actual path, or set via environment variable.
JSON_PATH = Path(
    os.getenv(
        "JSON_PATH",
        str(
            Path(__file__).parent.parent.parent
            / "data"
            / "datasets"
            / "latest"
            / "finetuning_dataset.json"
        ),
    )
)


class DataLayer:
    def __init__(self):
        self.source: str = "none"
        self._collection = None  # pymongo collection
        self._records: list[dict] = []  # in-memory JSON fallback
        self._connected: bool = False

    # ── Connection ────────────────────────────────────────────────────────

    def connect(self):
        if self._try_mongo():
            self.source = f"mongodb ({MONGO_DB}.{MONGO_COLL})"
        else:
            self._load_json()

    def _try_mongo(self) -> bool:
        try:
            from pymongo import MongoClient

            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            client.admin.command("ping")
            db = client[MONGO_DB]
            self._collection = db[MONGO_COLL]
            # Quick sanity: make sure the collection has documents
            if self._collection.count_documents({}) == 0:
                print("MongoDB reachable but collection is empty — using JSON.")
                return False
            print(f"MongoDB connected: {MONGO_URI}")
            return True
        except Exception as e:
            print(f"MongoDB unavailable ({e}) — falling back to JSON.")
            return False

    def _load_json(self):
        """Load finetuning_dataset.json into memory."""
        candidates = [
            JSON_PATH,
            Path(__file__).parent / "finetuning_dataset.json",
            Path(__file__).parent.parent / "finetuning_dataset.json",
        ]

        # Walk data/datasets/ recursively — handles nested structure:
        #   data/datasets/itseoa_dataset/<timestamp>/finetuning_dataset.json
        datasets_dir = Path(__file__).parent.parent.parent / "data" / "datasets"
        if datasets_dir.exists():
            all_matches = sorted(
                datasets_dir.rglob("finetuning_dataset.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            candidates = all_matches + candidates

        for path in candidates:
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    records = json.load(f)
                # Add a synthetic _id field for URL routing
                for i, r in enumerate(records):
                    r["_id"] = str(i)
                self._records = records
                self.source = f"json ({path})"
                print(f"Loaded JSON: {path}  ({len(records)} records)")
                return

        raise FileNotFoundError(
            f"No data found. Tried MongoDB and the following JSON paths:\n"
            + "\n".join(f"  {p}" for p in candidates)
            + "\n\nSet JSON_PATH environment variable to your finetuning_dataset.json"
        )

    # ── Queries ───────────────────────────────────────────────────────────

    def count(self) -> int:
        if self._collection is not None:
            return self._collection.count_documents({})
        return len(self._records)

    def list_pairs(
        self,
        skip: int = 0,
        limit: int = 20,
        query: str = "",
    ) -> tuple[list[dict], int]:
        """
        Returns (items, total) where items are lightweight dicts
        (no image_b64 — images are fetched separately via /image endpoint).
        """
        if self._collection is not None:
            return self._mongo_list(skip, limit, query)
        return self._json_list(skip, limit, query)

    def get_pair(self, pair_id: str) -> Optional[dict]:
        if self._collection is not None:
            return self._mongo_get(pair_id)
        return self._json_get(pair_id)

    # ── MongoDB implementation ─────────────────────────────────────────────

    def _mongo_list(self, skip, limit, query):
        from bson import ObjectId

        filter_ = {}
        if query:
            filter_ = {
                "$or": [
                    {"meta.defect": {"$regex": query, "$options": "i"}},
                    {"meta.fiche": {"$regex": query, "$options": "i"}},
                ]
            }

        total = self._collection.count_documents(filter_)
        cursor = (
            self._collection.find(
                filter_,
                {"image_b64": 0, "image_b64_thumb": 0},  # exclude heavy fields
            )
            .sort([("created_at", -1), ("_id", 1)])
            .skip(skip)
            .limit(limit)
        )

        items = []
        for doc in cursor:
            items.append(self._mongo_to_dict(doc, include_image=False))
        return items, total

    def _mongo_get(self, pair_id: str) -> Optional[dict]:
        from bson import ObjectId

        try:
            doc = self._collection.find_one({"_id": ObjectId(pair_id)})
        except Exception:
            doc = self._collection.find_one({"image_hash": pair_id})
        if not doc:
            return None
        return self._mongo_to_dict(doc, include_image=True)

    def _mongo_to_dict(self, doc: dict, include_image: bool) -> dict:
        meta = doc.get("meta", {})
        out = {
            "_id": str(doc["_id"]),
            "fiche": doc.get("fiche_number") or meta.get("fiche", ""),
            "defect": doc.get("defect_name") or meta.get("defect", ""),
            "page": doc.get("page") or meta.get("page", 0),
            "layout": doc.get("layout", "layout_a"),
            "source_pdf": doc.get("source_pdf", ""),
            "commentary": {
                "full": doc.get("commentary_full", ""),
                "intro": doc.get("commentary_intro", ""),
                "causes": doc.get("commentary_causes", ""),
                "gravite": doc.get("commentary_gravite", ""),
                "suites": doc.get("commentary_suites", ""),
            },
            "image_ext": doc.get("image_ext", "jpeg"),
        }
        if include_image:
            out["image_b64"] = doc.get("image_b64", "")
        return out

    # ── JSON implementation ────────────────────────────────────────────────

    def _json_list(self, skip, limit, query):
        records = list(reversed(self._records))  # newest first
        if query:
            q = query.lower()
            records = [
                r
                for r in records
                if q in r.get("meta", {}).get("defect", "").lower()
                or q in r.get("meta", {}).get("fiche", "").lower()
            ]
        total = len(records)
        items = []
        for r in records[skip : skip + limit]:
            items.append(self._json_to_dict(r, include_image=False))
        return items, total

    def _json_get(self, pair_id: str) -> Optional[dict]:
        for r in self._records:
            if r.get("_id") == pair_id:
                return self._json_to_dict(r, include_image=True)
        return None

    def _json_to_dict(self, r: dict, include_image: bool) -> dict:
        meta = r.get("meta", {})
        out = {
            "_id": r.get("_id", ""),
            "fiche": meta.get("fiche", ""),
            "defect": meta.get("defect", ""),
            "page": meta.get("page", 0),
            "layout": meta.get("layout", "layout_a"),
            "source_pdf": meta.get("source_pdf", ""),
            "commentary": {
                "full": r.get("response", ""),
                "intro": "",
                "causes": "",
                "gravite": "",
                "suites": "",
            },
            "image_ext": r.get("image_ext", "jpeg"),
        }
        # finetuning_dataset.json stores the full commentary as "response"
        # Try to split it into sections by the pipe separator used by extractor
        full = out["commentary"]["full"]
        if " | " in full:
            parts = [p.strip() for p in full.split(" | ")]
            keys = ["intro", "causes", "gravite", "suites"]
            for i, key in enumerate(keys):
                out["commentary"][key] = parts[i] if i < len(parts) else ""

        if include_image:
            out["image_b64"] = r.get("image_b64", "")
        return out

    def create_pair(self, record: dict) -> dict:
        """Insert a new pair and return the created record (without image_b64)."""
        if self._collection is not None:
            return self._mongo_create(record)
        return self._json_create(record)

    # ── MongoDB create ─────────────────────────────────────────────────────

    def _mongo_create(self, record: dict) -> dict:
        doc = {
            "created_at": datetime.utcnow(),
            "fiche_number": record["fiche"],
            "defect_name": record["defect"],
            "page": record["page"],
            "layout": record["layout"],
            "source_pdf": record["source_pdf"],
            "commentary_full": record["commentary"]["full"],
            "commentary_intro": record["commentary"]["intro"],
            "commentary_causes": record["commentary"]["causes"],
            "commentary_gravite": record["commentary"]["gravite"],
            "commentary_suites": record["commentary"]["suites"],
            "image_b64": record["image_b64"],
            "image_ext": record["image_ext"],
            "source_type": record["source_type"],
            "validated": record["validated"],
        }
        result = self._collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return self._mongo_to_dict(doc, include_image=False)

    # ── JSON create ────────────────────────────────────────────────────────

    def _json_create(self, record: dict) -> dict:
        new_id = str(len(self._records))
        new_record = {
            "_id": new_id,
            "meta": {
                "fiche": record["fiche"],
                "defect": record["defect"],
                "page": record["page"],
                "layout": record["layout"],
                "source_pdf": record["source_pdf"],
            },
            "response": record["commentary"]["full"],
            "image_b64": record["image_b64"],
            "image_ext": record["image_ext"],
        }
        self._records.insert(0, new_record)  # prepend so it appears first in list
        return self._json_to_dict(new_record, include_image=False)
