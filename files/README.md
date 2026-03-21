# ITSEOA Dataset Viewer

Simple viewer for the extracted training pairs.
FastAPI backend + Angular frontend.

## Quick start

### 1. Backend

```bash
cd viewer/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The backend will try MongoDB first (localhost:27017, db: inspection_db).
If MongoDB is not reachable it will automatically find and load the most
recent finetuning_dataset.json from data/datasets/.

To point it at a specific JSON file:
```bash
JSON_PATH=/path/to/finetuning_dataset.json uvicorn main:app --reload --port 8000
```

### 2. Frontend

```bash
# One-time setup (if you haven't created the Angular project yet)
cd viewer/frontend
npm install @angular/cli -g    # if not already installed
ng new viewer-frontend --standalone --style=css --routing=false
cd viewer-frontend

# Copy these files into the new project:
#   src/app/app.component.ts         → replace the generated one
#   src/app/app.config.ts            → replace the generated one
#   src/app/services/api.service.ts  → new file
#   src/app/components/viewer/       → new folder with 3 files
#   src/styles.css                   → replace the generated one

ng serve
```

Open http://localhost:4200

## File structure

```
viewer/
├── backend/
│   ├── main.py           ← FastAPI app, 4 endpoints
│   ├── data.py           ← MongoDB/JSON data layer
│   └── requirements.txt
└── frontend/
    └── src/app/
        ├── app.component.ts
        ├── app.config.ts
        ├── services/
        │   └── api.service.ts
        └── components/viewer/
            ├── viewer.component.ts
            ├── viewer.component.html
            └── viewer.component.css
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/status | Data source info + total count |
| GET | /api/pairs?page=1&limit=20&q= | Paginated pair list |
| GET | /api/pairs/{id} | Full pair detail + commentary |
| GET | /api/pairs/{id}/image | Raw image (use as img src) |
