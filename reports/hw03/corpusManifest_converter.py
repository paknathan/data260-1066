import hashlib
import json
import os

# Set paths relative to your script location
DATA_DIR = "./data"
OUTPUT_FILE = "CORPUS_MANIFEST.json"

manifest = []

if os.path.exists(DATA_DIR):
    for filename in os.listdir(DATA_DIR):
        filepath = os.path.join(DATA_DIR, filename)

        # Skip subdirectories or hidden Mac files like .DS_Store
        if os.path.isfile(filepath) and not filename.startswith("."):
            with open(filepath, "rb") as f:
                content = f.read()
                file_hash = hashlib.sha256(content).hexdigest()
                file_size = len(content)

            manifest.append(
                {
                    "filename": filename,
                    "byte_size": file_size,
                    "sha256": file_hash,
                }
            )

# Write output formatted nicely with 2-space indentation
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)

total_kb = sum(m["byte_size"] for m in manifest) / 1024
print(f"Successfully generated {OUTPUT_FILE}")
print(f"Total dataset size: {total_kb:.2f} KB")