"""
ITSEOA Extractor — Layout A Only
=================================
Extracts (image, commentary) training pairs from ITSEOA fascicule PDFs.

Targets Layout A pages only: single-fiche cards with a photo column on
the right and structured text (Causes, Gravité, Suites à donner) on the left.
Layout B (defect tables) is skipped — photo-to-row matching in tables is
unreliable and would pollute the dataset with wrong pairs.

Result: ~200+ clean, high-confidence training pairs per fascicule.

Usage:
    pip install pymupdf pillow pymongo tqdm
    python itseoa_extractor_final.py
"""

import fitz
import io, re, json, base64, hashlib
from pathlib import Path
from datetime import datetime
from collections import Counter
from tqdm import tqdm
from PIL import Image
import numpy as np
from dotenv import load_dotenv
import os

load_dotenv()

# ════════════════════════════════════════════════════════════
# CONFIG  ← only edit this section
# ════════════════════════════════════════════════════════════
PDF_PATH = (
    "/home/akstrov/Documents/studies/stage/CID/data/raw/ITSEOA_Fascicule21_web.pdf"
)
OUTPUT_DIR = Path(
    "/home/akstrov/Documents/studies/stage/CID/data/datasets/itseoa_dataset"
)  # runs saved as subfolders inside
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "inspection_db")
MONGO_COLL = os.getenv("MONGO_COLL", "itseoa_pairs")
# ════════════════════════════════════════════════════════════

RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
RUN_DIR = OUTPUT_DIR / RUN_ID
IMAGES_DIR = RUN_DIR / "images"
OUTPUT_DIR.mkdir(exist_ok=True)
RUN_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(exist_ok=True)

PROMPT_FR = (
    "Tu es un ingénieur civil spécialisé dans l'inspection des ouvrages d'art. "
    "Analyse cette image et rédige un commentaire d'inspection professionnel "
    "couvrant : le désordre observé, ses causes probables, sa gravité, "
    "et les suites à donner. Ne décris que ce qui est visuellement observable."
)


# ────────────────────────────────────────────────────────────
# UTILITIES
# ────────────────────────────────────────────────────────────


def img_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def is_real_photo(data: bytes, w: int, h: int) -> bool:
    """Accept any image that looks like a photograph. Reject icons and blank pages."""
    if w < 60 or h < 60:
        return False
    try:
        arr = np.array(
            Image.open(io.BytesIO(data)).convert("RGB").resize((48, 48)),
            dtype=np.float32,
        )
    except Exception:
        return False
    std = float(arr.std())
    white = float(np.all(arr > 235, axis=2).mean())
    if std < 10:
        return False
    if white > 0.85 and std < 35:
        return False
    return True


BOILERPLATE_RE = [
    re.compile(r"^\s*\d+\s*$"),
    re.compile(r"itseoa", re.IGNORECASE),
    re.compile(r"fascicule\s+\d+", re.IGNORECASE),
    re.compile(r"^\s*(setra|cerema)\b", re.IGNORECASE),
    re.compile(r"www\.", re.IGNORECASE),
    re.compile(r"^\s*\(\*+\)\s*rappel", re.IGNORECASE),
    re.compile(r"guide\s+d.application", re.IGNORECASE),
]


def clean(t: str) -> str:
    t = re.sub(r"\(cid:\d+\)", "", t)
    return re.sub(r"\s+", " ", t).strip()


def is_boilerplate(t: str) -> bool:
    return any(p.search(t) for p in BOILERPLATE_RE)


def get_text_blocks(page: fitz.Page, below_y: float = 0) -> list[dict]:
    out = []
    for b in page.get_text("dict").get("blocks", []):
        if b["type"] != 0 or b["bbox"][1] < below_y:
            continue
        text = clean(
            " ".join(span["text"] for line in b["lines"] for span in line["spans"])
        )
        if len(text) >= 3 and not is_boilerplate(text):
            out.append(
                {
                    "x0": b["bbox"][0],
                    "y0": b["bbox"][1],
                    "x1": b["bbox"][2],
                    "y1": b["bbox"][3],
                    "cx": (b["bbox"][0] + b["bbox"][2]) / 2,
                    "text": text,
                }
            )
    return out


def get_photos(page: fitz.Page, doc: fitz.Document, min_cx: float = 0) -> list[dict]:
    """Return real photos whose x-center is >= min_cx."""
    out = []
    for img_info in page.get_images(full=True):
        xref = img_info[0]
        try:
            bi = doc.extract_image(xref)
        except Exception:
            continue
        w, h, ext = bi["width"], bi["height"], bi["ext"].lower()
        data = bi["image"]
        if ext in ("svg", "xml") or not is_real_photo(data, w, h):
            continue
        bbox = fitz.Rect(0, 0, 0, 0)
        for rect in page.get_image_rects(xref):
            bbox = rect
            break
        cx = (bbox.x0 + bbox.x1) / 2
        if cx < min_cx:
            continue
        out.append(
            {
                "data": data,
                "ext": ext,
                "w": w,
                "h": h,
                "hash": img_hash(data),
                "x0": bbox.x0,
                "y0": bbox.y0,
                "x1": bbox.x1,
                "y1": bbox.y1,
            }
        )
    return sorted(out, key=lambda p: p["y0"])


# ────────────────────────────────────────────────────────────
# PAGE CLASSIFIER
# ────────────────────────────────────────────────────────────

RE_FICHE = re.compile(
    r"fiche\s+(\d+[.,]\d+)\s*[–—\-]?\s*(.{3,})",
    re.IGNORECASE,
)

SKIP_RE = [
    re.compile(r"comment\s+(lire|utiliser|interpréter)", re.IGNORECASE),
    re.compile(r"présentation\s+des\s+fiches", re.IGNORECASE),
    re.compile(r"intitulé\s+du\s+défaut", re.IGNORECASE),
    re.compile(r"description\s+éventuelle\s+du\s+défaut", re.IGNORECASE),
    re.compile(r"mode\s+d.emploi", re.IGNORECASE),
]

# Layout B table pages — classified but SKIPPED (not worth extracting)
LAYOUT_B_RE = [
    re.compile(r"causes?\s+possibles?\s+liées?\s+[àa]\s+l.ouv", re.IGNORECASE),
    re.compile(r"désordres?\s*\(\s*\*+\s*\)", re.IGNORECASE),
]


def classify_page(page: fitz.Page) -> tuple[str, str, str]:
    """
    Returns ('skip'|'layout_a'|'layout_b', fiche_number, fiche_title).
    Only layout_a pages are extracted. layout_b is detected but skipped.
    """
    pw, ph = page.rect.width, page.rect.height
    full = page.get_text("text")
    top = page.get_text("text", clip=fitz.Rect(0, 0, pw, ph * 0.25))

    for p in SKIP_RE:
        if p.search(full):
            return "skip", "", ""

    m = RE_FICHE.search(top)
    if not m:
        return "skip", "", ""

    num = m.group(1).replace(",", ".").strip()
    title = re.sub(r"\s+", " ", m.group(2)).strip().rstrip("–—-").strip()
    title = re.split(r"\s+fiche\s+\d", title, flags=re.IGNORECASE)[0].strip()

    for p in LAYOUT_B_RE:
        if p.search(full):
            return "layout_b", num, title  # detected, will be skipped in run()

    return "layout_a", num, title


# ────────────────────────────────────────────────────────────
# LAYOUT A EXTRACTOR
# ────────────────────────────────────────────────────────────

SECTION_RE = {
    "causes": re.compile(r"causes?\s+(probables?|possibles?)", re.IGNORECASE),
    "gravite": re.compile(r"gravit[ée]", re.IGNORECASE),
    "suites": re.compile(r"suites?\s+[àa]\s+donner", re.IGNORECASE),
}


def extract_layout_a(
    page: fitz.Page, doc: fitz.Document, fiche_num: str, defect_name: str
) -> list[dict]:
    """
    Extract training pairs from a Layout A fiche card page.

    Left column  (x < 55% page width): structured text split into sections.
    Right column (x > 55% page width): 1-4 photos stacked top to bottom.

    Every photo on the page gets the full structured commentary as its
    training target (intro | causes | gravité | suites à donner).
    """
    pw, ph = page.rect.width, page.rect.height
    split_x = pw * 0.55
    top_cut = ph * 0.18  # skip the fiche header zone

    # ── Left column: extract and split into sections ──────────────────────
    left_blocks = sorted(
        [b for b in get_text_blocks(page, below_y=top_cut) if b["cx"] < split_x],
        key=lambda b: b["y0"],
    )

    sections = {"intro": [], "causes": [], "gravite": [], "suites": []}
    current = "intro"
    for b in left_blocks:
        for sec, pat in SECTION_RE.items():
            if pat.search(b["text"]):
                current = sec
                break
        sections[current].append(b["text"])

    j = lambda parts: " ".join(parts).strip()
    intro = j(sections["intro"])
    causes = j(sections["causes"])
    gravite = j(sections["gravite"])
    suites = j(sections["suites"])
    full = " | ".join(v for v in [intro, causes, gravite, suites] if v)

    if len(full) < 15:
        return []

    # ── Right column: photos (x-center must be past split, with 15% slack) ─
    right_photos = get_photos(page, doc, min_cx=split_x * 0.85)

    if not right_photos:
        return []

    return [
        {
            "layout": "layout_a",
            "fiche_number": fiche_num,
            "defect_name": defect_name,
            "photo_index": idx,
            "has_photo": True,
            "image_data": photo["data"],
            "image_ext": photo["ext"],
            "image_w": photo["w"],
            "image_h": photo["h"],
            "image_hash": photo["hash"],
            "commentary_full": full,
            "commentary_intro": intro,
            "commentary_causes": causes,
            "commentary_gravite": gravite,
            "commentary_suites": suites,
        }
        for idx, photo in enumerate(right_photos)
    ]


# ────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────


def run():
    doc = fitz.open(PDF_PATH)
    print(f"Loaded : {PDF_PATH}  ({doc.page_count} pages)")
    print(f"Run ID : {RUN_ID}")
    print(f"Output : {RUN_DIR}\n")

    # ── Classify all pages ────────────────────────────────────────────────
    page_map = []
    for pn in range(doc.page_count):
        layout, fnum, title = classify_page(doc[pn])
        page_map.append((pn + 1, layout, fnum, title))

    counts = Counter(x[1] for x in page_map)
    print("Page classification:")
    for t, c in counts.most_common():
        label = t
        if t == "layout_b":
            label = "layout_b (skipped — table format, unreliable matching)"
        print(f"  {label:<55} : {c}")

    # ── Extract layout_a only ─────────────────────────────────────────────
    all_pairs = []
    seen_hashes = set()
    stats = Counter()

    for pn, layout, fnum, title in tqdm(page_map, desc="Extracting"):
        page = doc[pn - 1]

        if layout != "layout_a":
            stats[f"skipped_{layout}"] += 1
            continue

        pairs = extract_layout_a(page, doc, fnum, title)
        stats["layout_a_pages"] += 1

        for p in pairs:
            h = p["image_hash"]
            if h in seen_hashes:
                stats["duplicates"] += 1
                continue
            seen_hashes.add(h)
            p["source_pdf"] = Path(PDF_PATH).name
            p["page"] = pn
            all_pairs.append(p)
            stats["pairs"] += 1

    print(f"\n=== EXTRACTION COMPLETE ===")
    print(f"Layout A pages processed : {stats['layout_a_pages']}")
    print(f"Training pairs extracted : {stats['pairs']}")
    print(f"Duplicates removed       : {stats['duplicates']}")
    avg = stats["pairs"] / max(stats["layout_a_pages"], 1)
    print(f"Avg photos per fiche     : {avg:.1f}")

    # ── Defect type summary ───────────────────────────────────────────────
    defect_counts = Counter(p["defect_name"] for p in all_pairs)
    print(f"\nDefect types ({len(defect_counts)} unique):")
    for defect, count in defect_counts.most_common(15):
        bar = "█" * count
        print(f"  {bar} ({count})  {defect[:65]}")
    if len(defect_counts) > 15:
        print(f"  ... and {len(defect_counts) - 15} more")

    # ── Commentary quality stats ──────────────────────────────────────────
    lengths = [len(p["commentary_full"]) for p in all_pairs]
    has_all_sections = sum(
        1
        for p in all_pairs
        if p["commentary_causes"] and p["commentary_gravite"] and p["commentary_suites"]
    )
    print(f"\nCommentary quality:")
    print(f"  Avg length          : {sum(lengths) // len(lengths)} chars")
    print(f"  Min / Max           : {min(lengths)} / {max(lengths)} chars")
    print(f"  All 4 sections      : {has_all_sections}/{len(all_pairs)} pairs")

    # ── MongoDB (optional) ────────────────────────────────────────────────
    collection = None
    if MONGO_URI:
        try:
            from pymongo import MongoClient

            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            client.admin.command("ping")
            db = client[DB_NAME]
            collection = db[COLL_NAME]
            for idx in ["image_hash", "fiche_number", "defect_name"]:
                collection.create_index(idx)
            print(f"\nMongoDB connected: {DB_NAME}.{COLL_NAME}")
        except Exception as e:
            print(f"\nMongoDB unavailable ({e}) — JSON only.")

    # ── Save ──────────────────────────────────────────────────────────────
    json_records = []
    ft_records = []
    inserted = 0

    for p in tqdm(all_pairs, desc="Saving"):
        fname = (
            f"fiche{p['fiche_number']}_p{p['page']}_"
            f"idx{p['photo_index']}_{p['image_hash']}.{p['image_ext']}"
        )
        (IMAGES_DIR / fname).write_bytes(p["image_data"])

        if collection is not None:
            try:
                rec = {k: v for k, v in p.items() if k != "image_data"}
                rec["image_b64"] = base64.b64encode(p["image_data"]).decode()
                rec["image_file"] = fname
                collection.update_one(
                    {"image_hash": p["image_hash"]},
                    {"$setOnInsert": rec},
                    upsert=True,
                )
                inserted += 1
            except Exception:
                pass

        ft_records.append(
            {
                "image_b64": base64.b64encode(p["image_data"]).decode(),
                "image_ext": p["image_ext"],
                "prompt": PROMPT_FR,
                "response": p["commentary_full"],
                "meta": {
                    "fiche": p["fiche_number"],
                    "defect": p["defect_name"],
                    "page": p["page"],
                    "photo_index": p["photo_index"],
                    "source_pdf": p["source_pdf"],
                },
            }
        )

        meta = {k: v for k, v in p.items() if k != "image_data"}
        meta["image_file"] = fname
        json_records.append(meta)

    # Write JSON files
    for fname, data in [
        ("all_pairs.json", json_records),
        ("finetuning_dataset.json", ft_records),
    ]:
        path = RUN_DIR / fname
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Saved {len(data):>4} records → {RUN_DIR.name}/{fname}")

    if collection is not None:
        print(f"MongoDB inserted: {inserted}")

    print(f"\nDone.")
    print(f"  Fine-tuning dataset : {len(ft_records)} pairs → finetuning_dataset.json")
    print(f"  Full metadata       : {len(json_records)} records → all_pairs.json")
    print(f"  Images              : {IMAGES_DIR}")
    print(f"\nTo use on the next fascicule:")
    print(f"  Change PDF_PATH in the CONFIG section and run again.")
    print(f"  Each run creates a new folder: {OUTPUT_DIR}/<timestamp>/")


if __name__ == "__main__":
    run()
