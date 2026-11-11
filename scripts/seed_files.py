"""Write placeholder bytes for the files rows in db/seed.sql, so the demo
can download them. Sizes match files.size_bytes in the seed.

Used by `make db-reset`. Writes under UPLOAD_DIR (default <repo>/uploads,
which is gitignored and never served directly).
"""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
upload_dir = pathlib.Path(os.environ.get("UPLOAD_DIR", ROOT / "uploads"))

SEED_FILES = {
    "pixel/f1-homepage-v2.fig": 1024,     # client-visible, on "Homepage mockups"
    "pixel/f2-internal-notes.pdf": 2048,  # internal, same task
}

for key, size in SEED_FILES.items():
    path = upload_dir / key
    path.parent.mkdir(parents=True, exist_ok=True)
    label = f"AgencyDesk demo file: {key}\n".encode()
    path.write_bytes((label * (size // len(label) + 1))[:size])
print(f"wrote {len(SEED_FILES)} seed files under {upload_dir}")
