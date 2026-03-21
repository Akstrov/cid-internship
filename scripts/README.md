# Scripts

## itseoa_extractor.py
Extracts (image, commentary) training pairs from ITSEOA fascicule PDFs.
Handles Layout A pages (single fiche cards with photos + structured text).

Usage:
    pip install pymupdf pillow pymongo tqdm
    python itseoa_extractor.py

Configure PDF_PATH and OUTPUT_DIR at the top of the file.
Each run creates a new timestamped folder in OUTPUT_DIR.
