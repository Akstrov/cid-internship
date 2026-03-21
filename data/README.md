# Data

## raw/
Reference PDFs — ITSEOA fascicules and DT375 IQOA catalog.
These are the source documents for dataset extraction.

## datasets/
Extracted training datasets. Each subfolder is one extraction run
(timestamped). Use the most recent run's finetuning_dataset.json
for fine-tuning.

To extract more data, run: scripts/itseoa_extractor.py
(change PDF_PATH to point at the desired fascicule)
